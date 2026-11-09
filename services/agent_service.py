"""QA and Edit mode orchestration."""

import json
import re
import sqlite3
import time
from types import SimpleNamespace
from typing import Any

from openai import OpenAI
import requests

from config import settings
from services.db_service import execute_read_sql, execute_write_sql
from services.graph.graph_build import refresh_graph_from_db
from services.graph.graph_query import (
    add_semantic_join, get_subgraph, is_date_related_question, save_verified_query,
)

# Hold the one proposed edit until it is accepted.
_pending_edit = None
USE_VERIFIED_QUERIES = True


def _client():
    if settings.llm_provider == "gemini":
        return OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return OpenAI(
        api_key="ollama" if settings.llm_provider == "ollama" else settings.openai_api_key,
        base_url=settings.ollama_base_url if settings.llm_provider == "ollama" else settings.openai_base_url,
    )


def _complete(messages, tools=None, tool_choice="auto"):
    if settings.llm_provider != "claude":
        options = {"tools": tools, "tool_choice": tool_choice} if tools else {}
        if tools and settings.llm_provider != "gemini":
            options.update(reasoning_effort="none", parallel_tool_calls=False)
        client = _client()
        if tools and settings.llm_provider == "gemini":
            raw = client.chat.completions.with_raw_response.create(
                model=settings.llm_model, messages=messages, **options
            ).http_response.json()
            result = raw["choices"][0]["message"]
            calls = [SimpleNamespace(
                id=call["id"], type="function", extra_content=call.get("extra_content"),
                function=SimpleNamespace(**call["function"]),
            ) for call in result.get("tool_calls", [])]
            usage = SimpleNamespace(**raw["usage"]) if raw.get("usage") else None
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=result.get("content"), tool_calls=calls or None,
                ))], usage=usage,
            )
        return client.chat.completions.create(
            model=settings.llm_model, messages=messages, **options
        )

    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    claude_messages = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "tool":
            content = [{"type": "tool_result", "tool_use_id": message["tool_call_id"],
                        "content": message["content"]}]
            role = "user"
        elif role == "assistant" and message.get("tool_calls"):
            content = ([{"type": "text", "text": message["content"]}]
                       if message.get("content") else [])
            content.extend({"type": "tool_use", "id": call["id"],
                            "name": call["function"]["name"],
                            "input": json.loads(call["function"]["arguments"])}
                           for call in message["tool_calls"])
        else:
            content = message.get("content") or ""
        if claude_messages and claude_messages[-1]["role"] == role:
            previous = claude_messages[-1]["content"]
            claude_messages[-1]["content"] = (previous if isinstance(previous, list) else [
                {"type": "text", "text": previous}
            ]) + (content if isinstance(content, list) else [{"type": "text", "text": content}])
        else:
            claude_messages.append({"role": role, "content": content})

    body = {"model": settings.llm_model, "max_tokens": 4096, "messages": claude_messages}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [{"name": tool["function"]["name"],
                          "description": tool["function"].get("description", ""),
                          "input_schema": tool["function"]["parameters"]} for tool in tools]
        body["tool_choice"] = {"type": "any" if tool_choice == "required" else "auto"}
    response = requests.post(
        f"{settings.anthropic_base_url.rstrip('/')}/messages",
        headers={"x-api-key": settings.anthropic_api_key,
                 "anthropic-version": "2023-06-01"}, json=body, timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    text = "\n".join(block["text"] for block in result["content"] if block["type"] == "text")
    calls = [SimpleNamespace(
        id=block["id"], type="function",
        function=SimpleNamespace(name=block["name"], arguments=json.dumps(block["input"])),
    ) for block in result["content"] if block["type"] == "tool_use"]
    usage = SimpleNamespace(prompt_tokens=result["usage"]["input_tokens"],
                            completion_tokens=result["usage"]["output_tokens"],
                            total_tokens=result["usage"]["input_tokens"] + result["usage"]["output_tokens"])
    message = SimpleNamespace(content=text, tool_calls=calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _chat(messages, usage=None):
    response = _complete(messages)
    if usage is not None and response.usage:
        usage["prompt_tokens"] += response.usage.prompt_tokens
        usage["completion_tokens"] += response.usage.completion_tokens
        usage["total_tokens"] += response.usage.total_tokens
    return response.choices[0].message.content


def _token_usage():
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _sql_from_response(content, mode):
    # Remove optional model markdown so the result can be parsed or executed.
    text = re.sub(r"```(?:json|sql)?", "", content or "", flags=re.I).replace("```", "").strip()
    if mode == "qa":
        # Preserve CTEs: a read-only query may start with WITH and end in SELECT.
        match = re.match(r"(?:WITH|SELECT)\b.*", text, re.I | re.S)
        if not match:
            match = re.search(r"\bSELECT\b.*", text, re.I | re.S)
        if not match:
            raise ValueError("The model did not return a SELECT or WITH query")
        return match.group(0).strip().rstrip(";") + ";"

    # Edit responses are plans: either an allowed SQL operation or a graph join.
    plan = json.loads(text)
    if plan.get("kind") == "sql":
        sql = plan["sql"].strip()
        if not re.match(r"^(INSERT|UPDATE|DELETE|ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE)\b", sql, re.I):
            raise ValueError("Unsupported Edit SQL operation")
        plan["sql"] = sql.rstrip(";") + ";"
    elif plan.get("kind") != "semantic_join":
        raise ValueError("Edit plan must be SQL or a semantic join")
    return plan


def _generate_sql(prompt, context, mode="qa", error=None, failed_sql=None, usage=None, trace=None):
    # Use a different output format for read-only questions and proposed edits.
    instruction = (
        "Return one executable, read-only SQLite query starting with SELECT or WITH. "
        "Return only requested columns; don't include helper or aggregate columns unless asked."
        if mode == "qa" else
        'Return one JSON plan: {"kind":"sql","sql":"...","summary":"..."} '
        'or {"kind":"semantic_join","from_table":"...","from_column":"...",'
        '"to_table":"...","to_column":"...","description":"..."}. '
        "SQL must be one INSERT, UPDATE, DELETE, ALTER TABLE, CREATE TABLE, or DROP TABLE."
    )
    if mode == "qa" and is_date_related_question(prompt):
        instruction += (
            " For date filters, follow any DATE FORMAT shown in the schema context. "
            "Use SQLite date functions only when the stored format is compatible; "
            "otherwise filter using the stored text format."
        )
    # QA can send a failed query and SQLite's error back for one repair attempt.
    repair = f"\nRepair this SQL: {failed_sql}\nSQLite error: {error}" if error else ""
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"Question: {prompt}\nSchema context:\n{context}{repair}"},
    ]
    if trace is not None:
        trace["prompt"] = messages
    content = _chat(messages, usage)
    return _sql_from_response(content, mode)


def synthesize_answer(prompt, rows, usage=None):
    # Summarize only the first 50 result rows to keep the answer prompt compact.
    content = _chat([{"role": "user", "content": "\n".join([
            "Answer the user's question using only these database results.",
            f"Question: {prompt}", f"Results: {json.dumps(rows[:50], default=str)}",
            "Be concise and do not invent values.",
    ])}], usage)
    return content.strip()


def _explain_edit(prompt, plan, usage=None):
    content = _chat([
        {"role": "system", "content": "Briefly explain what this proposed edit will change. Do not say it has already been applied."},
        {"role": "user", "content": f"Request: {prompt}\nProposed edit: {plan}"},
    ], usage)
    return content.strip()


def answer_question(db_name: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    # Retrieve graph context before asking the model to generate SQL.
    started = time.perf_counter()
    usage = _token_usage()
    db_path = settings.data_dir / (db_name if db_name.endswith(".sqlite") else f"{db_name}.sqlite")
    subgraph = get_subgraph(db_path.stem, prompt, USE_VERIFIED_QUERIES)
    sql = _generate_sql(prompt, subgraph["prompt_context_str"], "qa", usage=usage)
    retried = False
    try:
        # Execute against the sandbox copy; retry once if SQLite rejects the SQL.
        rows = execute_read_sql(db_path, sql)
    except sqlite3.Error as error:
        retried = True
        sql = _generate_sql(prompt, subgraph["prompt_context_str"], "qa", error, sql, usage)
        try:
            rows = execute_read_sql(db_path, sql)
        except sqlite3.Error as retry_error:
            retry_error.generated_sql = sql
            raise

    # Store successful SQL as graph memory for later related questions.
    touched = [table["id"] for table in subgraph["tables"] if table["name"].lower() in sql.lower()]
    if USE_VERIFIED_QUERIES:
        save_verified_query(db_path.stem, prompt, sql, touched)
    answer = synthesize_answer(prompt, rows, usage)
    return {
        "answer": answer, "sql": sql, "rows": rows, "subgraph": subgraph,
        "telemetry": {"total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                      "retried": retried, **usage},
    }


def run_edit_flow(db_name, prompt):
    """Create a proposal without applying it."""
    global _pending_edit

    # Use the same subgraph context as QA, then save the proposed action for approval.
    usage = _token_usage()
    db_path = settings.data_dir / (db_name if db_name.endswith(".sqlite") else f"{db_name}.sqlite")
    subgraph = get_subgraph(db_path.stem, prompt, USE_VERIFIED_QUERIES)
    plan = _generate_sql(prompt, subgraph["prompt_context_str"], "edit", usage=usage)
    if plan["kind"] == "semantic_join":
        # Build the join condition from the two table-column pairs in the plan.
        plan["join_condition"] = f"{plan['from_table']}.{plan['from_column']} = {plan['to_table']}.{plan['to_column']}"
    plan_summary = plan.get("summary", "")
    plan["summary"] = _explain_edit(prompt, plan, usage)
    _pending_edit = (db_path.stem, plan)
    return {
        "status": "awaiting_confirmation",
        "kind": plan["kind"], "summary": plan.get("summary", "Review this proposed change."),
        "plan_summary": plan_summary,
        "sql": plan.get("sql"), "join_condition": plan.get("join_condition"), "subgraph": subgraph,
        "telemetry": usage,
    }


def apply_edit(db_name):
    """Apply a proposal after the user accepts it."""
    global _pending_edit

    # Look up the accepted plan and ensure it belongs to the selected database.
    db_path = settings.data_dir / (db_name if db_name.endswith(".sqlite") else f"{db_name}.sqlite")
    if _pending_edit is None:
        raise ValueError("There is no edit awaiting approval")
    db, plan = _pending_edit
    if db != db_path.stem:
        raise ValueError("Edit proposal belongs to a different database")

    result = {"status": "applied", "kind": plan["kind"], "summary": plan.get("summary", "Edit applied."),
              "sql": plan.get("sql"), "rows_affected": 0, "graph_updated": False}
    if plan["kind"] == "semantic_join":
        # Relationship-only edits are saved directly to Neo4j.
        add_semantic_join(db, plan["from_table"], plan["to_table"], plan["join_condition"], plan.get("description", ""))
        result.update(graph_updated=True, join_condition=plan["join_condition"])
    else:
        # Database edits run on the working copy; structural changes also refresh Neo4j.
        result["rows_affected"] = execute_write_sql(db_path, plan["sql"])
        if re.match(r"^\s*(ALTER|CREATE|DROP)\s+TABLE\b", plan["sql"], re.I):
            try:
                _, result["graph"] = refresh_graph_from_db(db, db_path)
                result["graph_updated"] = True
            except Exception as error:
                result.update(status="applied_with_sync_error", graph_error=str(error))
    _pending_edit = None
    return result
