"""Small Neo4j HTTP Query API v2 client."""

import requests

from config import settings


def graph_elements(db_name, metadata):
	"""Convert SQLite metadata to the frontend node/edge format."""
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


def run_cypher_http(statement, params=None):
	# Keep Cypher static and send all values through parameters.
	payload = {
		"statement": " ".join(statement.splitlines()),
		"parameters": params or {},
	}
	try:
		response = requests.post(
			settings.neo4j_http_url,
			auth=(settings.neo4j_user, settings.neo4j_password),
			json=payload,
			timeout=30,
		)
		if response.status_code >= 400:
			try:
				error = response.json().get("errors", [{}])[0]
				message = error.get("message", response.text)
			except ValueError:
				message = response.text
			raise RuntimeError(f"Neo4j query failed ({response.status_code}): {message}")
		response.raise_for_status()
		return handle_neo4j_res(response)
	except requests.RequestException as error:
		raise RuntimeError(f"Neo4j HTTP request failed: {error}") from error


def handle_neo4j_res(response):
	# Normalize both read responses and write responses from Query API v2.
	body = response.json() if hasattr(response, "json") else response
	if body.get("errors"):
		error = body["errors"][0]
		raise RuntimeError(f"Neo4j query failed: {error.get('message', error)}")
	data = body.get("data", {})
	fields = data.get("fields", body.get("fields", [])) if isinstance(data, dict) else body.get("fields", [])
	values = data.get("values", []) if isinstance(data, dict) else data
	return [
		dict(zip(fields, row)) if fields and isinstance(row, list) else row
		for row in values
	]
