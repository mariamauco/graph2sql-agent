"""Public graph-service facade."""

from .graph_build import build_graph as _build_graph
from .graph_client import handle_neo4j_res, run_cypher_http
from .graph_query import (
    add_semantic_join as _add_semantic_join,
    get_subgraph as _get_subgraph,
    save_verified_query as _save_verified_query,
)


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
