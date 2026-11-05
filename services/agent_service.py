"""QA and Edit mode orchestration."""

import re
import sqlite3
import time
from typing import Any

from openai import OpenAI

from config import settings
from services.db_service import execute_read_sql
from services.graph.graph_service import get_subgraph, save_verified_query, synthesize_answer


def _client():
    # Ollama exposes the same chat-completions API as OpenAI.
    return OpenAI(
        api_key="ollama" if settings.llm_provider == "ollama" else settings.openai_api_key,
        base_url=settings.ollama_base_url if settings.llm_provider == "ollama" else settings.openai_base_url,
    )


def _sql_from_response(content):
    # Local coding models commonly wrap SQL in markdown fences.
    sql = re.sub(r"```(?:sql)?", "", content, flags=re.I).replace("```", "").strip()
    match = re.search(r"\bSELECT\b.*", sql, re.I | re.S)
    if not match:
        raise ValueError("The model did not return a SELECT query")
    return match.group(0).strip().rstrip(";") + ";"


def _generate_sql(prompt, context, error=None, failed_sql=None):
    repair = ""
    if error:
        repair = f"\nRepair this SQL: {failed_sql}\nSQLite error: {error}"
    response = _client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": "Return only one executable SQLite SELECT query."},
            {"role": "user", "content": f"Question: {prompt}\nSchema context:\n{context}{repair}"},
        ],
    )
    return _sql_from_response(response.choices[0].message.content)

def answer_question(db_name: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    """Run the graph-assisted QA pipeline."""
    started = time.perf_counter()
    db_path = settings.data_dir / (db_name if db_name.endswith(".sqlite") else f"{db_name}.sqlite")
    subgraph = get_subgraph(db_path.stem, prompt)
    sql = _generate_sql(prompt, subgraph["prompt_context_str"])
    retried = False
    try:
        rows = execute_read_sql(db_path, sql)
    except sqlite3.Error as error:
        retried = True
        sql = _generate_sql(prompt, subgraph["prompt_context_str"], error, sql)
        rows = execute_read_sql(db_path, sql)

    touched = [table["id"] for table in subgraph["tables"] if table["name"].lower() in sql.lower()]
    save_verified_query(db_path.stem, prompt, sql, touched)
    answer = synthesize_answer(prompt, sql, rows, subgraph["prompt_context_str"])
    return {
        "answer": answer, "sql": sql, "rows": rows, "subgraph": subgraph,
        "telemetry": {"total_latency_ms": round((time.perf_counter() - started) * 1000, 2), "retried": retried},
    }


def apply_edit(db_name: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    """Run the validated database or semantic-graph edit pipeline."""
    raise NotImplementedError
