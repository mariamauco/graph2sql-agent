"""Run resumable Spider benchmark evaluations."""

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Make project modules importable when this file is run as a script.
sys.path.insert(0, str(ROOT))

from config import settings
from services.agent_service import _client, _generate_sql, _sql_from_response, _token_usage
from services.graph.graph_build import refresh_graph_from_db
from services.graph.graph_query import get_subgraph, save_verified_query
from services.graph.graph_client import run_cypher_http

TRAIN_FILE = ROOT / "data" / "spider_databases" / "train_spider.json"
RESULTS_DIR = Path(__file__).parent / "results"
JSON_FILE = RESULTS_DIR / "benchmarks.json"
CSV_FILE = RESULTS_DIR / "benchmarks.csv"
TRACE_FILE = RESULTS_DIR / "test_b_traces.json"
FIELDS = [
    "testmode", "status", "queryid", "db_id", "query", "question",
    "question_toks_length", "query_toks_length", "latency_ms",
    "prompt_tokens", "completion_tokens", "total_tokens", "accuracy",
    "generated_sql", "graph_tables_count", "test_c_version", "error",
]


def _key(row):
    """Identify a saved result by mode and Spider record index."""
    return row.get("testmode"), str(row.get("queryid"))


def _load_results():
    # Merge CSV and JSON so a partial write to either file can be resumed.
    rows = {}
    if CSV_FILE.exists():
        with CSV_FILE.open(newline="") as file:
            rows.update((_key(row), row) for row in csv.DictReader(file))
    if JSON_FILE.exists():
        try:
            rows.update((_key(row), row) for row in json.loads(JSON_FILE.read_text()))
        except (json.JSONDecodeError, TypeError):
            pass
    return list(rows.values())


def _save_results(rows):
    """Rewrite both result files from the current set of benchmark rows."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_FILE.write_text(json.dumps(rows, indent=2))
    with CSV_FILE.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        # Flatten multiline text so each benchmark result stays on one CSV line.
        writer.writerows({
            key: value.replace("\r", " ").replace("\n", " ") if isinstance(value, str) else value
            for key, value in row.items()
        } for row in rows)


def _save_test_b_trace(trace):
    """Save one trace per Test B query, replacing an earlier attempt."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    traces = json.loads(TRACE_FILE.read_text()) if TRACE_FILE.exists() else []
    traces = [row for row in traces if row["queryid"] != trace["queryid"]]
    traces.append(trace)
    TRACE_FILE.write_text(json.dumps(traces, indent=2, default=str))


def flush_memory(db_name):
    """Clear saved query memory for one benchmark graph."""
    run_cypher_http(
        "MATCH (q:VerifiedQuery {db_name: $db_name}) DETACH DELETE q",
        {"db_name": db_name},
    )


def _source_database(db_id):
    """Find the Spider source DB, or a selected/test DB copy as fallback."""
    candidates = [
        settings.data_dir / "spider_databases" / "database" / db_id / f"{db_id}.sqlite",
        settings.data_dir / f"{db_id}.sqlite",
        settings.data_dir / "spider_databases" / "test_database" / db_id / f"{db_id}.sqlite",
    ]
    if source := next((path for path in candidates if path.is_file()), None):
        return source
    raise FileNotFoundError(f"Spider database not found for {db_id}")


def _working_database(db_id, copied):
    """Copy each database once per run into an isolated benchmark working folder."""
    if db_id not in copied:
        destination = settings.data_dir / "working" / "benchmarks" / f"{db_id}.sqlite"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_source_database(db_id), destination)
        copied.add(db_id)
    return settings.data_dir / "working" / "benchmarks" / f"{db_id}.sqlite"


def _schema(db_path):
    """Read user-created DDL from SQLite; no separate schema.sql is needed."""
    with sqlite3.connect(db_path) as connection:
        statements = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type IN ('table', 'index', 'view', 'trigger') "
            "AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
    return "\n\n".join(statement[0] for statement in statements)


def _missing_database_row(query_id, example, error, testmode):
    """Record a skipped query when its source SQLite database is unavailable."""
    return {
        "testmode": testmode, "status": "missing_database", "queryid": query_id,
        "db_id": example["db_id"], "query": example["query"],
        "question": example["question"],
        "question_toks_length": len(example.get("question_toks") or []),
        "query_toks_length": len(example.get("query_toks") or []),
        "latency_ms": None, "prompt_tokens": None, "completion_tokens": None,
        "total_tokens": None, "accuracy": None, "generated_sql": "", "error": str(error),
    }


def _execute(db_path, sql):
    """Run one SQL statement and return its rows for result comparison."""
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA query_only = ON")
        return connection.execute(sql).fetchall()


def test_a(query_id, example, db_path):
    """Use the raw SQLite schema to generate and evaluate one SQL query."""
    # Count tokens reported by the model for all calls made by Test A.
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    started = time.perf_counter()
    # Test A uses the complete schema as context and makes no graph queries.
    generated_sql = _generate_sql(example["question"], _schema(db_path), "qa", usage=usage)
    error = ""
    # A SQL execution error makes this prediction incorrect, but still records the run.
    try:
        predicted = set(_execute(db_path, generated_sql))
    except sqlite3.Error as exc:
        predicted, error = set(), str(exc)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    # Spider execution accuracy compares unordered result sets.
    try:
        expected = set(_execute(db_path, example["query"]))
        accuracy = float(not error and predicted == expected)
    except sqlite3.Error as exc:
        accuracy, error = 0.0, error or f"Gold SQL failed: {exc}"

    return {
        "testmode": "test_a", "status": "completed", "queryid": query_id,
        "db_id": example["db_id"],
        "query": example["query"], "question": example["question"],
        "question_toks_length": len(example.get("question_toks") or []),
        "query_toks_length": len(example.get("query_toks") or []),
        "latency_ms": latency_ms, **usage, "accuracy": accuracy,
        "generated_sql": generated_sql, "error": error,
    }


def test_b(query_id, example, db_path):
    """Let the model inspect SQLite with up to three SQL tool calls, then score its SQL."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    started = time.perf_counter()
    trace = {
        "queryid": query_id, "db_id": example["db_id"],
        "question": example["question"], "events": [],
    }
    messages = [
        {"role": "system", "content": (
            "Answer the database question by inspecting SQLite with query_sqlite. "
            "Use no more than three inspection calls. Then return one executable, "
            "read-only SQLite query starting with SELECT or WITH."
        )},
        {"role": "user", "content": example["question"]},
    ]
    tools = [{"type": "function", "function": {
        "name": "query_sqlite",
        "description": "Run a read-only SELECT query against the SQLite database.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A SQLite SELECT query."}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    }}]
    generated_sql = None

    # Require one inspection first, then let the model inspect or produce final SQL.
    for call_number in range(3):
        response = _client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=tools,
            tool_choice="required" if call_number == 0 else "auto",
            parallel_tool_calls=False,
            reasoning_effort="none",
        )
        if response.usage:
            usage["prompt_tokens"] += response.usage.prompt_tokens
            usage["completion_tokens"] += response.usage.completion_tokens
            usage["total_tokens"] += response.usage.total_tokens

        message = response.choices[0].message
        if not message.tool_calls:
            try:
                generated_sql = _sql_from_response(message.content, "qa")
            except ValueError:
                # If the model explained its findings instead, request SQL explicitly below.
                messages.append({"role": "assistant", "content": message.content or ""})
            break

        messages.append({
            "role": "assistant", "content": message.content,
            "tool_calls": [call.model_dump(exclude_none=True) for call in message.tool_calls],
        })
        for tool_call in message.tool_calls:
            sql = ""
            try:
                sql = json.loads(tool_call.function.arguments)["sql"]
                if not sql.lstrip().upper().startswith("SELECT"):
                    raise ValueError("Only SELECT queries are allowed for inspection")
                result = _execute(db_path, sql)[:20]
                trace["events"].append({
                    "type": "tool_result", "sql": sql, "result": result,
                })
            except (ValueError, KeyError, sqlite3.Error) as error:
                result = {"error": str(error)}
                trace["events"].append({
                    "type": "tool_error", "sql": sql or tool_call.function.arguments,
                    "error": str(error),
                })
            messages.append({
                "role": "tool", "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

    # If the third call was still an inspection, request the final SQL without tools.
    if generated_sql is None:
        messages.append({"role": "system", "content": "Return one read-only SQLite query starting with SELECT or WITH."})
        response = _client().chat.completions.create(model=settings.llm_model, messages=messages)
        if response.usage:
            usage["prompt_tokens"] += response.usage.prompt_tokens
            usage["completion_tokens"] += response.usage.completion_tokens
            usage["total_tokens"] += response.usage.total_tokens
        generated_sql = _sql_from_response(response.choices[0].message.content, "qa")

    error = ""
    try:
        predicted = set(_execute(db_path, generated_sql))
    except sqlite3.Error as exc:
        predicted, error = set(), str(exc)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    try:
        expected = set(_execute(db_path, example["query"]))
        accuracy = float(not error and predicted == expected)
    except sqlite3.Error as exc:
        accuracy, error = 0.0, error or f"Gold SQL failed: {exc}"

    trace["events"].append({"type": "final_sql", "sql": generated_sql})
    trace["accuracy"] = accuracy
    _save_test_b_trace(trace)

    return {
        "testmode": "test_b", "status": "completed", "queryid": query_id,
        "db_id": example["db_id"], "query": example["query"],
        "question": example["question"],
        "question_toks_length": len(example.get("question_toks") or []),
        "query_toks_length": len(example.get("query_toks") or []),
        "latency_ms": latency_ms, **usage, "accuracy": accuracy,
        "generated_sql": generated_sql, "error": error,
    }


def test_c(query_id, example, db_path):
    """Generate from graph context, execute, and save the successful query as memory."""
    started = time.perf_counter()
    usage = _token_usage()
    graph_name = f"benchmark_{db_path.stem}"
    subgraph = get_subgraph(graph_name, example["question"])
    sql = _generate_sql(example["question"], subgraph["prompt_context_str"], "qa", usage=usage)
    error = ""
    try:
        predicted = set(_execute(db_path, sql))
    except sqlite3.Error as exc:
        predicted, error = set(), str(exc)
    try:
        expected = set(_execute(db_path, example["query"]))
        accuracy = float(not error and predicted == expected)
    except sqlite3.Error as exc:
        accuracy, error = 0.0, error or f"Gold SQL failed: {exc}"
    if accuracy:
        touched = [table["id"] for table in subgraph["tables"] if table["name"].lower() in sql.lower()]
        save_verified_query(graph_name, example["question"], sql, touched)

    return {
        "testmode": "test_c", "status": "completed", "queryid": query_id,
        "db_id": example["db_id"], "query": example["query"],
        "question": example["question"],
        "question_toks_length": len(example.get("question_toks") or []),
        "query_toks_length": len(example.get("query_toks") or []),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        **usage, "accuracy": accuracy,
        "generated_sql": sql, "error": error,
    }


def evaluate(n, testmode="test_a"):
    """Run a benchmark mode over the first n Spider examples, resuming saved rows."""
    # Existing results are retained, and completed query IDs count toward n.
    examples = json.loads(TRAIN_FILE.read_text())
    rows = _load_results()
    completed = {
        _key(row) for row in rows
        if row.get("status") != "missing_database"
        and (testmode != "test_c" or (
            row.get("test_c_version") == 3 and row.get("graph_tables_count")
        ))
    }
    copied = set()
    graph_table_counts = {}
    memory_flushed = set()
    run_test = {"test_a": test_a, "test_b": test_b, "test_c": test_c}[testmode]

    for query_id, example in enumerate(examples):
        # Limit by dataset position, so skipped results do not extend the run.
        if query_id >= n:
            break
        key = (testmode, str(query_id))
        if key in completed:
            print(f"skip query {query_id}")
            continue

        try:
            working_db = _working_database(example["db_id"], copied)
        except FileNotFoundError as error:
            row = _missing_database_row(query_id, example, error, testmode)
            print(f"{example['db_id']} query {query_id}: skipped (missing SQLite)")
        else:
            try:
                if testmode == "test_c" and example["db_id"] not in memory_flushed:
                    flush_memory(f"benchmark_{example['db_id']}")
                    memory_flushed.add(example["db_id"])
                if testmode == "test_c" and example["db_id"] not in graph_table_counts:
                    _, graph = refresh_graph_from_db(f"benchmark_{example['db_id']}", working_db)
                    if not graph["tables_count"]:
                        raise RuntimeError(f"No tables found while building graph for {example['db_id']}")
                    graph_table_counts[example["db_id"]] = graph["tables_count"]
                row = run_test(query_id, example, working_db)
            except Exception as error:
                if testmode != "test_c":
                    raise
                row = {
                    "testmode": testmode, "status": "error", "queryid": query_id,
                    "db_id": example["db_id"], "query": example["query"],
                    "question": example["question"],
                    "question_toks_length": len(example.get("question_toks") or []),
                    "query_toks_length": len(example.get("query_toks") or []),
                    "latency_ms": None, "prompt_tokens": None, "completion_tokens": None,
                    "total_tokens": None, "accuracy": 0.0,
                    "generated_sql": getattr(error, "generated_sql", ""), "error": str(error),
                }
            if testmode == "test_c":
                row["graph_tables_count"] = graph_table_counts.get(example["db_id"])
                row["test_c_version"] = 3

        # Replace any earlier missing marker if the row is retried after data is added.
        rows = [saved for saved in rows if _key(saved) != key]
        rows.append(row)
        completed.add(key)
        _save_results(rows)
        if row["status"] == "completed":
            print(f"{example['db_id']} query {query_id}: accuracy={row['accuracy']}")

    return rows


def main():
    """Parse the requested number of Spider queries and run the selected benchmark."""
    parser = argparse.ArgumentParser(description="Run a Spider benchmark mode")
    parser.add_argument("--n", type=int, required=True, help="number of initial train_spider queries to process")
    parser.add_argument("--testmode", choices=("test_a", "test_b", "test_c"), default="test_a")
    args = parser.parse_args()
    evaluate(args.n, args.testmode)


if __name__ == "__main__":
    main()
