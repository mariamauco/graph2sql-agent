"""QA and Edit mode orchestration."""

import json
import re
import sqlite3
import time
from typing import Any

from openai import OpenAI

from config import settings
from services.db_service import execute_read_sql, execute_write_sql
from services.graph.graph_build import refresh_graph_from_db
from services.graph.graph_query import add_semantic_join, get_subgraph, save_verified_query

# Hold the one proposed edit until it is accepted.
_pending_edit = None


def _client():
    # Both configured providers use the OpenAI-compatible chat completions API.
    return OpenAI(
        api_key="ollama" if settings.llm_provider == "ollama" else settings.openai_api_key,
        base_url=settings.ollama_base_url if settings.llm_provider == "ollama" else settings.openai_base_url,
    )


def _chat(messages, usage=None):
    response = _client().chat.completions.create(model=settings.llm_model, messages=messages)
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


def _generate_sql(prompt, context, mode="qa", error=None, failed_sql=None, usage=None):
    # Use a different output format for read-only questions and proposed edits.
    instruction = (
        "Return one executable, read-only SQLite query starting with SELECT or WITH."
        if mode == "qa" else
        'Return one JSON plan: {"kind":"sql","sql":"...","summary":"..."} '
        'or {"kind":"semantic_join","from_table":"...","from_column":"...",'
        '"to_table":"...","to_column":"...","description":"..."}. '
        "SQL must be one INSERT, UPDATE, DELETE, ALTER TABLE, CREATE TABLE, or DROP TABLE."
    )
    # QA can send a failed query and SQLite's error back for one repair attempt.
    repair = f"\nRepair this SQL: {failed_sql}\nSQLite error: {error}" if error else ""
    content = _chat([
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"Question: {prompt}\nSchema context:\n{context}{repair}"},
    ], usage)
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
    subgraph = get_subgraph(db_path.stem, prompt)
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
    subgraph = get_subgraph(db_path.stem, prompt)
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
