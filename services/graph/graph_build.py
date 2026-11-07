"""Neo4j schema graph construction helpers."""

import re
from difflib import get_close_matches

from config import settings
from services.aliases_map import DB_ALIASES
from .graph_client import run_cypher_http


def create_schema_index():
	# Index names, aliases, and safe sample values for prompt matching.
	return run_cypher_http(
		"CREATE FULLTEXT INDEX schema_index IF NOT EXISTS "
		"FOR (n:Table|Column) ON EACH [n.name, n.aliases, n.sample_values]"
	)


def get_aliases(name):
	words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).lower().split("_")
	aliases = set(words + [name.lower()])
	for word in words:
		for abbreviation, meanings in DB_ALIASES.items():
			candidates = [abbreviation, *meanings]
			if word == abbreviation or word in meanings:
				aliases.update(meanings)
			elif len(word) >= 3 and get_close_matches(word, candidates, n=1, cutoff=0.8):
				aliases.update(meanings)
	aliases.discard("tbl")
	aliases.discard("mstr")
	return sorted(aliases)


def upsert_database(db_name):
	# MERGE makes setup safe to run repeatedly.
	return run_cypher_http("MERGE (d:Database {name: $db_name})", {"db_name": db_name})


def upsert_table(db_name, table):
	table_name = table["name"]
	return run_cypher_http(
		"MERGE (t:Table {id: $id}) SET t.db_name = $db_name, t.name = $name, "
		"t.aliases = $aliases, t.row_count = $row_count, t.ddl_summary = $ddl_summary "
		"WITH t MATCH (d:Database {name: $db_name}) MERGE (d)-[:HAS_TABLE]->(t)",
		{
			"id": f"{db_name}.{table_name}", "db_name": db_name, "name": table_name,
			"aliases": get_aliases(table_name), "row_count": table.get("row_count", 0),
			"ddl_summary": table.get("ddl_summary", ""),
		},
	)


def upsert_column(db_name, table_name, column):
	# The SQLite profiler omits sensitive samples; enforce it again here.
	samples = [] if re.search(
		r"password|secret|token|ssn|email|phone|address", column["name"], re.I
	) else column.get("sample_values", [])
	return run_cypher_http(
		"MERGE (c:Column {id: $id}) SET c.db_name = $db_name, c.table_name = $table_name, "
		"c.name = $name, c.data_type = $data_type, c.is_pk = $is_pk, "
		"c.is_nullable = $is_nullable, c.sample_values = $sample_values, c.aliases = $aliases "
		"WITH c MATCH (t:Table {id: $table_id}) MERGE (t)-[:HAS_COLUMN]->(c)",
		{
			"id": f"{db_name}.{table_name}.{column['name']}", "db_name": db_name,
			"table_name": table_name, "name": column["name"],
			"data_type": column.get("type", ""),
			"is_pk": column.get("is_pk", column.get("pk", False)),
			"is_nullable": column.get("is_nullable", not column.get("notnull", False)),
			"sample_values": samples, "aliases": get_aliases(column["name"]),
			"table_id": f"{db_name}.{table_name}",
		},
	)


def _upsert_foreign_key(db_name, table_name, foreign_key):
	# Store a column edge and a direct table join hint for path finding.
	ref_table = foreign_key["ref_table"]
	from_col = foreign_key["from_col"]
	to_col = foreign_key["to_col"]
	join = f"{table_name}.{from_col} = {ref_table}.{to_col}"
	return run_cypher_http(
		"MATCH (a:Column {id: $from_id}), (b:Column {id: $to_id}) "
		"MERGE (a)-[:FOREIGN_KEY {from_col: $from_col, to_col: $to_col}]->(b) "
		"WITH a, b MATCH (ta:Table {id: $from_table}), (tb:Table {id: $to_table}) "
		"MERGE (ta)-[r:REFERENCES_TABLE {join_condition: $join}]->(tb) "
		"SET r.join_condition = $join",
		{
			"from_id": f"{db_name}.{table_name}.{from_col}",
			"to_id": f"{db_name}.{ref_table}.{to_col}", "from_col": from_col,
			"to_col": to_col, "from_table": f"{db_name}.{table_name}",
			"to_table": f"{db_name}.{ref_table}", "join": join,
		},
	)


def build_graph(db_name, metadata):
	"""Create/update nodes, relationships, and the full-text index."""
	cache_path = settings.data_dir / "working" / f"{db_name}_graph.json"
	try:
		cache_path.unlink()
	except FileNotFoundError:
		pass

	# Create nodes before relationships so every endpoint exists.
	upsert_database(db_name)
	for table in metadata.get("tables", []):
		upsert_table(db_name, table)
		for column in table.get("columns", []):
			upsert_column(db_name, table["name"], column)

	foreign_keys = [
		(table["name"], foreign_key)
		for table in metadata.get("tables", [])
		for foreign_key in table.get("foreign_keys", [])
	]
	for table_name, foreign_key in foreign_keys:
		_upsert_foreign_key(db_name, table_name, foreign_key)
	create_schema_index()

	tables = metadata.get("tables", [])
	columns = sum(len(table.get("columns", [])) for table in tables)
	return {
		"tables_count": len(tables), "columns_count": columns,
		"foreign_keys_count": len(foreign_keys),
		"edges_count": len(tables) + columns + len(foreign_keys) * 2,
	}
