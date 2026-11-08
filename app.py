"""Flask entry point for the graph-assisted text-to-SQL workbench."""

import json
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from config import settings
from services.agent_service import answer_question, apply_edit, run_edit_flow
from services.db_service import provide_working
from services.graph.graph_build import refresh_graph_from_db
from services.graph.graph_client import graph_elements


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return jsonify({"status": "ok"})

    @app.get("/api/databases")
    def databases():
        names = sorted(path.stem for path in settings.data_dir.glob("*.sqlite"))
        return jsonify({"databases": names})

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

        cache_path = settings.data_dir / "working" / f"{db_path.stem}_graph.json"
        if cache_path.is_file():
            return jsonify({**json.loads(cache_path.read_text()), "cached": True})

        try:
            metadata, summary = refresh_graph_from_db(db_path.stem, db_path)
            nodes, edges = graph_elements(db_path.stem, metadata)
        except sqlite3.Error as error:
            return jsonify({"error": f"SQLite setup failed: {error}"}), 400
        except RuntimeError as error:
            return jsonify({
                "error": str(error),
                "hint": "Check that Neo4j is running and reachable.",
            }), 503
        except Exception as error:
            return jsonify({"error": f"Graph setup failed: {error}"}), 500

        result = {
            "status": "ready",
            "db_name": db_path.stem,
            "nodes": nodes,
            "edges": edges,
            **summary,
            "cached": False,
        }
        cache_path.parent.mkdir(exist_ok=True)
        cache_path.write_text(json.dumps(result))
        return jsonify(result)

    @app.post("/api/reset")
    def reset():
        payload = request.get_json(silent=True) or {}
        if not payload.get("db_name"):
            return jsonify({"error": "db_name is required"}), 400
        filename = Path(payload.get("db_name", "")).name
        filename = filename if filename.endswith(".sqlite") else f"{filename}.sqlite"
        db_path = settings.data_dir / filename
        if not db_path.is_file():
            return jsonify({"error": f"Database not found: {filename}"}), 404
        provide_working(db_path, reset=True)
        (settings.data_dir / "working" / f"{db_path.stem}_graph.json").unlink(missing_ok=True)
        return jsonify({"status": "working database reset"})

    @app.errorhandler(503)
    def service_unavailable(error):
        return jsonify({"error": str(error), "hint": "Check Neo4j and LLM services."}), 503

    @app.post("/api/agent/qa")
    def qa():
        payload = request.get_json(silent=True) or {}
        if not payload.get("db_name") or not payload.get("prompt"):
            return jsonify({"error": "db_name and prompt are required"}), 400
        try:
            return jsonify(answer_question(payload["db_name"], payload["prompt"]))
        except sqlite3.Error as error:
            return jsonify({"error": f"SQLite query failed: {error}"}), 400
        except RuntimeError as error:
            return jsonify({"error": str(error), "hint": "Check the configured LLM and Neo4j services."}), 503

    @app.post("/api/agent/edit")
    def edit():
        payload = request.get_json(silent=True) or {}
        if not payload.get("db_name") or not payload.get("prompt"):
            return jsonify({"error": "db_name and prompt are required"}), 400
        try:
            return jsonify(run_edit_flow(payload["db_name"], payload["prompt"]))
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 404
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except RuntimeError as error:
            return jsonify({"error": str(error), "hint": "Check the configured LLM and Neo4j services."}), 503

    @app.post("/api/agent/edit/accept")
    def accept_edit():
        payload = request.get_json(silent=True) or {}
        if not payload.get("db_name"):
            return jsonify({"error": "db_name is required"}), 400
        try:
            return jsonify(apply_edit(payload["db_name"]))
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 404
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        except sqlite3.Error as error:
            return jsonify({"error": f"SQLite edit failed: {error}"}), 400
        except RuntimeError as error:
            return jsonify({"error": str(error), "hint": "Check the configured LLM and Neo4j services."}), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
