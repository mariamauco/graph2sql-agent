"""Neo4j HTTP Query API v2 client and graph builders."""

from typing import Any


def build_graph(db_name, metadata) -> dict[str, int]:
    """Build or refresh the schema graph for a database."""
    raise NotImplementedError


def get_subgraph(db_name, prompt, k) -> dict[str, Any]:
    """Find relevant tables, join paths, columns, and verified queries."""
    raise NotImplementedError


def save_verified_query(db_name, prompt, sql, touched_tables):
    """Persist a successful query and its table references."""
    raise NotImplementedError


def add_semantic_join(
    db_name,
    from_table,
    to_table,
    join_condition,
    description):
    """Persist a user-confirmed semantic relationship."""
    raise NotImplementedError
