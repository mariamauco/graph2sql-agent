"""Flask entry point for the graph-assisted text-to-SQL workbench."""

import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from config import settings
from services.db_service import extract_schema
from services.graph.graph_service import build_graph


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return jsonify({"status": "ok"})

    @app.get("/api/databases")
    def databases():
        names = sorted(path.stem for path in settings.data_dir.glob("*.sqlite"))
        return jsonify({"databases": names, "active_db": None})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/setup")
    def setup():
        payload = request.get_json(silent=True) or {}
        requested_name = payload.get("db_name")
        if not requested_name:
            return jsonify({"error": "db_name is required"}), 400

        # Accept both "college_1" and "college_1.sqlite" from the UI.
        filename = Path(requested_name).name
        filename = filename if filename.endswith(".sqlite") else f"{filename}.sqlite"
        db_path = settings.data_dir / filename
        if not db_path.is_file():
            return jsonify({"error": f"Database not found: {filename}"}), 404

        try:
            # SQLite metadata feeds the Neo4j graph builder.
            metadata = extract_schema(db_path)
            summary = build_graph(db_path.stem, metadata)
        except sqlite3.Error as error:
            return jsonify({"error": f"SQLite setup failed: {error}"}), 400
        except RuntimeError as error:
            return jsonify({
                "error": str(error),
                "hint": "Check that Neo4j is running and reachable.",
            }), 503

        return jsonify({"status": "ready", "db_name": db_path.stem, **summary})

    @app.errorhandler(503)
    def service_unavailable(error):
        return jsonify({"error": str(error), "hint": "Check Neo4j and LLM services."}), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
