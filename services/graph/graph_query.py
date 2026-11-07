"""Neo4j graph retrieval and query-memory helpers."""

import hashlib
import re

from .graph_client import run_cypher_http


def _search_query(prompt):
	# Keep stop words and Lucene punctuation out of the full-text query.
	stop_words = {"a", "an", "and", "are", "for", "from", "how", "is", "of", "the", "to", "what"}
	words = [word for word in re.findall(r"[a-zA-Z0-9_]+", prompt.lower()) if word not in stop_words]
	return " OR ".join(f'"{word}"' for word in words) or "*"


def _join_paths(table_ids):
	# This traverses schema edges; SQLite performs the eventual row join.
	return run_cypher_http(
		"UNWIND $table_ids AS from_id UNWIND $table_ids AS to_id "
		"WITH from_id, to_id WHERE from_id < to_id "
		"MATCH (a:Table {id: from_id}), (b:Table {id: to_id}) "
		"MATCH p = allShortestPaths((a)-[:REFERENCES_TABLE|SEMANTIC_JOIN*..3]-(b)) "
		"UNWIND range(0, size(nodes(p)) - 2) AS i "
		"WITH relationships(p)[i] AS r, nodes(p)[i] AS from, nodes(p)[i + 1] AS to "
		"WHERE r.join_condition IS NOT NULL "
		"RETURN DISTINCT from.name AS from_table, to.name AS to_table, r.join_condition AS join_condition",
		{"table_ids": table_ids},
	)


def _table_context(table_ids):
	# Fetch tables and columns together, then restore the nested Python shape.
	rows = run_cypher_http(
		"MATCH (t:Table) WHERE t.id IN $table_ids OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column) "
		"RETURN t.id AS id, t.name AS name, t.aliases AS aliases, t.row_count AS row_count, "
		"c.name AS column_name, c.data_type AS data_type, c.is_pk AS is_pk, "
		"c.is_nullable AS is_nullable, c.sample_values AS sample_values ORDER BY t.name, c.name",
		{"table_ids": table_ids},
	)
	tables = {}
	for row in rows:
		table = tables.setdefault(row["id"], {
			"id": row["id"], "name": row["name"], "aliases": row.get("aliases", []),
			"row_count": row.get("row_count", 0), "columns": [],
		})
		if row.get("column_name") is not None:
			table["columns"].append({
				"name": row["column_name"], "type": row.get("data_type", ""),
				"is_pk": row.get("is_pk", False), "is_nullable": row.get("is_nullable", True),
				"sample_values": row.get("sample_values", []),
			})
	return list(tables.values())


def _context_string(tables, joins, verified):
	# Keep the prompt context compact and explicit.
	lines = ["Tables:"]
	lines.extend(f"- {t['name']}: {', '.join(c['name'] for c in t['columns'])}" for t in tables)
	lines.append("Join paths:")
	lines.extend(f"- {join['join_condition']}" for join in joins)
	if verified:
		lines.append("Verified queries:")
		lines.extend(f"- {query['prompt']}: {query['sql']}" for query in verified)
	return "\n".join(lines)


def get_subgraph(db_name, prompt, k=5):
	# Use all tables for small schemas; search only larger schemas.
	all_tables = run_cypher_http(
		"MATCH (t:Table {db_name: $db_name}) RETURN t.id AS id ORDER BY t.name",
		{"db_name": db_name},
	)
	if len(all_tables) <= 5:
		table_ids = [row["id"] for row in all_tables]
	else:
		hits = run_cypher_http(
			"CALL db.index.fulltext.queryNodes('schema_index', $query) YIELD node, score "
			"WHERE node.db_name = $db_name OPTIONAL MATCH (owner:Table)-[:HAS_COLUMN]->(node) "
			"WITH coalesce(owner, node) AS table, max(score) AS score WHERE table IS NOT NULL "
			"RETURN table.id AS id ORDER BY score DESC LIMIT $limit",
			{"query": _search_query(prompt), "db_name": db_name, "limit": k},
		)
		table_ids = [row["id"] for row in hits] or [row["id"] for row in all_tables]

	tables = _table_context(table_ids)
	joins = _join_paths(table_ids)
	verified = run_cypher_http(
		"MATCH (q:VerifiedQuery)-[:TOUCHES]->(t:Table) WHERE t.id IN $table_ids "
		"WITH q, max(q.created_at) AS created_at ORDER BY created_at DESC "
		"RETURN q.prompt AS prompt, q.sql AS sql LIMIT 2",
		{"table_ids": table_ids},
	)
	return {
		"tables": tables, "join_paths": joins, "verified_queries": verified,
		"prompt_context_str": _context_string(tables, joins, verified),
	}


def save_verified_query(db_name, prompt, sql, touched_tables):
	query_id = hashlib.sha256(f"{db_name}:{prompt}:{sql}".encode()).hexdigest()
	# Save only successful queries and connect them to the tables they used.
	return run_cypher_http(
		"MERGE (q:VerifiedQuery {id: $id}) SET q.db_name = $db_name, q.prompt = $prompt, "
		"q.sql = $sql, q.created_at = datetime() WITH q UNWIND $tables AS table_id "
		"MATCH (t:Table {id: table_id}) MERGE (q)-[:TOUCHES]->(t)",
		{"id": query_id, "db_name": db_name, "prompt": prompt, "sql": sql, "tables": touched_tables},
	)


def add_semantic_join(db_name, from_table, to_table, join_condition, description):
	# User-confirmed joins become future shortest-path edges.
	return run_cypher_http(
		"MATCH (a:Table {id: $from_id}), (b:Table {id: $to_id}) "
		"MERGE (a)-[r:SEMANTIC_JOIN {join_condition: $join_condition}]->(b) "
		"SET r.description = $description, r.created_by = 'user'",
		{"from_id": f"{db_name}.{from_table}", "to_id": f"{db_name}.{to_table}",
		 "join_condition": join_condition, "description": description},
	)
