#!/usr/bin/env python3
"""Exercise and report the confirmation-based Edit flow on college_1."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import sys
import traceback
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

DB_NAME = "college_1"
DB_PATH = REPOSITORY / "data" / f"{DB_NAME}.sqlite"
TEST_TABLE = "EDIT_FLOW_TEST"


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def show(title, value):
    print(f"\n{'=' * 12} {title} {'=' * 12}")
    print(json.dumps(value, indent=2, default=str))


def source_hash():
    return hashlib.sha256(DB_PATH.read_bytes()).hexdigest()


def database_state(db_path):
    from services.db_service import extract_schema

    metadata = extract_schema(db_path)
    return [{
        "name": table["name"],
        "columns": [{"name": column["name"], "type": column["type"], "primary_key": column["is_pk"]}
                    for column in table["columns"]],
        "foreign_keys": table["foreign_keys"],
    } for table in metadata["tables"]]


def graph_state():
    from services.graph.graph_client import run_cypher_http

    tables = run_cypher_http(
        "MATCH (t:Table {db_name: $db_name}) OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column) "
        "RETURN t.name AS name, collect(c.name) AS columns ORDER BY name",
        {"db_name": DB_NAME},
    )
    relationships = run_cypher_http(
        "MATCH (a)-[r]->(b) WHERE a.db_name = $db_name AND b.db_name = $db_name "
        "RETURN labels(a) AS from_labels, a.name AS from_name, a.table_name AS from_table, "
        "type(r) AS type, labels(b) AS to_labels, b.name AS to_name, b.table_name AS to_table, "
        "properties(r) AS properties ORDER BY type, from_name, to_name",
        {"db_name": DB_NAME},
    )

    def endpoint(row, side):
        name = row[f"{side}_name"]
        return name if "Table" in row[f"{side}_labels"] else f"{row[f'{side}_table']}.{name}"

    return {
        "tables": tables,
        "relationships": [{
            "type": row["type"], "from": endpoint(row, "from"), "to": endpoint(row, "to"),
            "properties": row["properties"],
        } for row in relationships],
    }


def main():
    from services.agent_service import apply_edit, run_edit_flow
    from services.db_service import execute_write_sql, provide_working
    from services.graph.graph_build import refresh_graph_from_db

    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    original_hash = source_hash()
    working_path = provide_working(DB_PATH)

    # Start from a clean baseline if a previous run left its test table behind.
    execute_write_sql(working_path, f"DROP TABLE IF EXISTS {TEST_TABLE};")
    _, setup_summary = refresh_graph_from_db(DB_NAME, working_path)
    show("Graph baseline refresh", setup_summary)
    show("Before: working SQLite schema", database_state(working_path))
    before_graph = graph_state()
    show("Before: Neo4j graph", before_graph)
    show("Source database SHA-256 before", original_hash)

    prompt = (
        f"Create a table named {TEST_TABLE} with an integer primary key column "
        "EDIT_TEST_ID and a text column EDIT_NOTE."
    )
    proposal = run_edit_flow(DB_NAME, prompt)
    show("Edit proposal", {
        "status": proposal["status"],
        "kind": proposal["kind"],
        "summary": proposal["summary"],
        "plan_summary": proposal.get("plan_summary"),
        "sql": proposal.get("sql"),
        "join_condition": proposal.get("join_condition"),
        "context_tables": [table["name"] for table in proposal["subgraph"]["tables"]],
    })

    if proposal["kind"] != "sql" or not proposal.get("sql", "").upper().startswith("CREATE TABLE"):
        raise AssertionError(f"Expected CREATE TABLE proposal, got {proposal.get('sql')!r}")

    applied = apply_edit(DB_NAME)
    show("Accepted edit result", applied)
    after_database = database_state(working_path)
    after_graph = graph_state()
    show("After: working SQLite schema", after_database)
    show("After: Neo4j graph", after_graph)

    db_tables = {table["name"].upper(): table for table in after_database}
    graph_tables = {table["name"].upper(): table for table in after_graph["tables"]}
    assert TEST_TABLE in db_tables, f"{TEST_TABLE} missing from working database"
    assert {"EDIT_TEST_ID", "EDIT_NOTE"}.issubset(
        {column["name"].upper() for column in db_tables[TEST_TABLE]["columns"]}
    ), "Expected test columns missing from working database"
    assert TEST_TABLE in graph_tables, f"{TEST_TABLE} missing from Neo4j"
    assert {"EDIT_TEST_ID", "EDIT_NOTE"}.issubset(
        {column.upper() for column in graph_tables[TEST_TABLE]["columns"]}
    ), "Expected test columns missing from Neo4j"
    assert applied["graph_updated"], "Graph was not reported as synchronized"
    assert source_hash() == original_hash, "Source college_1.sqlite was modified"

    show("Verification", {
        "working_database_has_test_table": True,
        "neo4j_has_test_table": True,
        "neo4j_schema_synced": applied["graph_updated"],
        "source_database_unchanged": True,
        "status": "PASS",
    })


if __name__ == "__main__":
    output_path = Path(__file__).with_suffix(".out")
    with output_path.open("w") as output:
        tee = Tee(sys.stdout, output)
        with redirect_stdout(tee), redirect_stderr(tee):
            try:
                main()
            except Exception:
                traceback.print_exc(file=sys.stdout)
                raise
    print(f"Output saved to {output_path}")
