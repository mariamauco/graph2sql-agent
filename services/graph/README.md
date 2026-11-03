# Graph Service

This package builds and queries the Neo4j schema graph. The public entry point is
`graph_service.py`; implementation details are split into three small modules.

## Modules

```text
graph_client.py   Neo4j HTTP Query API v2 requests and response handling
graph_build.py    Database, table, column, relationship, and index setup
graph_query.py    Full-text search, shortest paths, context, and query memory
graph_service.py  Public facade used by the rest of the application
```

Callers should use the facade:

```python
from services.graph.graph_service import build_graph, get_subgraph
```

## Setup Flow

SQLite metadata from `db_service.extract_schema()` is passed to:

```text
metadata
   |
   v
build_graph()
   |
   +--> Database node
   +--> Table nodes and aliases
   +--> Column nodes and safe sample values
   +--> FOREIGN_KEY and REFERENCES_TABLE edges
   +--> schema_index full-text index
```

The builder uses Cypher `MERGE`, so running setup repeatedly updates existing
nodes and relationships instead of duplicating them.

The graph contains:

```text
(Database)-[:HAS_TABLE]->(Table)
(Table)-[:HAS_COLUMN]->(Column)
(Column)-[:FOREIGN_KEY]->(Column)
(Table)-[:REFERENCES_TABLE]->(Table)
(Table)-[:SEMANTIC_JOIN]->(Table)
(VerifiedQuery)-[:TOUCHES]->(Table)
```

Table and column aliases are generated from identifier words and the shared
`services/aliases_map.py` abbreviation dictionary. Safe low-cardinality text
values are stored as `Column.sample_values`; sensitive columns are excluded.

## Query Flow

`get_subgraph(db_name, prompt, k=5)` performs these steps:

1. Lists the database's tables.
2. Uses `schema_index` to find matching tables and columns for larger schemas.
3. Maps matching columns to their parent tables and keeps the top `k` anchors.
4. Falls back to all tables when the database has five or fewer tables or the search has no hits.
5. Runs `allShortestPaths` across `REFERENCES_TABLE` and `SEMANTIC_JOIN` edges.
6. Returns the selected tables, columns, sample values, explicit join conditions, and up to two verified queries.
7. Formats the result as `prompt_context_str` for the LLM.

Neo4j discovers the schema route. SQLite performs the actual row join later
when the generated SQL executes.

The returned shape is:

```python
{
    "tables": [...],
    "join_paths": [...],
    "verified_queries": [...],
    "prompt_context_str": "...",
}
```

## Query Memory

After a successful SQL execution, `save_verified_query()` stores the prompt and
SQL as a `VerifiedQuery` node and connects it to the tables used. Future
subgraph requests retrieve up to two matching verified queries as few-shot
examples.

`add_semantic_join()` stores a user-confirmed relationship when SQLite does
not contain the relevant foreign key. That edge is then available to future
shortest-path searches.

## HTTP Client

All Neo4j access goes through `graph_client.run_cypher_http()`:

```python
{
    "statement": "MATCH ... RETURN ...",
    "parameters": {"value": "..."},
}
```

Cypher values must be parameters, not string-interpolated user input. The
client uses `NEO4J_HTTP_URL`, `NEO4J_USER`, and `NEO4J_PASSWORD` from the
application configuration.

## Testing

Compile the package:

```bash
python3 -m py_compile services/graph/*.py
```

The graph modules can be tested without Neo4j by replacing
`graph_client.run_cypher_http` or the imported module helper with a mocked
function that returns representative rows. A live integration test requires
Neo4j to be running through Docker Compose.
