"""Public graph-service facade."""

from .graph_build import build_graph as _build_graph
from .graph_client import handle_neo4j_res, run_cypher_http
from .graph_query import (
    add_semantic_join as _add_semantic_join,
    get_subgraph as _get_subgraph,
    save_verified_query as _save_verified_query,
)


def graph_elements(db_name, metadata):
    """Convert SQLite metadata to Cytoscape's node/edge format."""
    nodes = []
    edges = []
    for table in metadata.get("tables", []):
        table_name = table["name"]
        table_id = f"{db_name}.{table_name}"
        nodes.append({"data": {"id": table_id, "label": table_name, "type": "table"}})
        for column in table.get("columns", []):
            column_id = f"{table_id}.{column['name']}"
            nodes.append({"data": {"id": column_id, "label": column["name"], "type": "column"}})
            edges.append({"data": {
                "id": f"has-column:{column_id}", "source": table_id,
                "target": column_id, "type": "HAS_COLUMN",
            }})
        for foreign_key in table.get("foreign_keys", []):
            source = f"{table_id}.{foreign_key['from_col']}"
            target_table = f"{db_name}.{foreign_key['ref_table']}"
            target = f"{target_table}.{foreign_key['to_col']}"
            join = f"{table_name}.{foreign_key['from_col']} = " \
                f"{foreign_key['ref_table']}.{foreign_key['to_col']}"
            edges.extend([
                {"data": {
                    "id": f"foreign-key:{source}:{target}", "source": source,
                    "target": target, "label": join, "type": "FOREIGN_KEY",
                }},
                {"data": {
                    "id": f"references:{table_id}:{target_table}", "source": table_id,
                    "target": target_table, "label": join, "type": "REFERENCES_TABLE",
                }},
            ])
    return nodes, edges


def build_graph(db_name, metadata):
    # Keep graph setup behind the original public function.
    return _build_graph(db_name, metadata)


def get_subgraph(db_name, prompt, k=5):
    # Keep prompt retrieval behind the original public function.
    return _get_subgraph(db_name, prompt, k)


def save_verified_query(db_name, prompt, sql, touched_tables):
    return _save_verified_query(db_name, prompt, sql, touched_tables)


def add_semantic_join(db_name, from_table, to_table, join_condition, description):
    return _add_semantic_join(db_name, from_table, to_table, join_condition, description)
