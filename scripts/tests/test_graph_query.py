#!/usr/bin/env python3
"""Verbose end-to-end check for one Spider question and the graph pipeline."""

import argparse
from contextlib import redirect_stdout
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from services.db_service import execute_read_sql, extract_schema
from services.agent_service import synthesize_answer
from services.graph.graph_build import build_graph
from services.graph.graph_client import graph_elements
from services.graph.graph_query import get_subgraph


DATASET = REPOSITORY / "data" / "spider_databases" / "dev.json"


class Tee:
    """Write test output to both the terminal and the .out file."""

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


def database_path(db_id):
    for path in (
        REPOSITORY / "data" / f"{db_id}.sqlite",
        REPOSITORY / "data" / "spider_databases" / "database" / db_id / f"{db_id}.sqlite",
    ):
        if path.is_file():
            return path
    raise FileNotFoundError(f"SQLite database not found for {db_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, default=0, help="dev.json entry index")
    parser.add_argument("--db", help="override the entry database id")
    args = parser.parse_args()

    entries = json.loads(DATASET.read_text())
    entry = entries[args.index]
    db_id = args.db or entry["db_id"]
    db_path = database_path(db_id)
    gold_sql = entry["query"]

    show("1. Spider question", {
        "index": args.index,
        "db_id": db_id,
        "question": entry["question"],
        "query": gold_sql,
        "parsed_sql": entry["sql"],
    })

    metadata = extract_schema(db_path)
    show("2. SQLite metadata", metadata)

    nodes, edges = graph_elements(db_id, metadata)
    show("3. Frontend graph elements", {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    })

    summary = build_graph(db_id, metadata)
    show("4. Neo4j build summary", summary)

    subgraph = get_subgraph(db_id, entry["question"])
    show("5. Retrieved graph context", subgraph)

    rows = execute_read_sql(db_path, gold_sql)
    show("6. Gold SQL execution", {
        "sql": gold_sql,
        "row_count": len(rows),
        "rows": rows,
    })

    show("7. LLM answer synthesis", {
        "answer": synthesize_answer(
            entry["question"], rows
        )
    })

    print("\nGraph query test completed.")


if __name__ == "__main__":
    output_path = Path(__file__).with_suffix(".out")
    with output_path.open("w") as output, redirect_stdout(Tee(sys.stdout, output)):
        main()
    print(f"Output saved to {output_path}")
