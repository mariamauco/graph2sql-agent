"""Small Neo4j HTTP Query API v2 client."""

import requests

from config import settings


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
