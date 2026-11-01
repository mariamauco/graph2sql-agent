"""Flask entry point for the graph-assisted text-to-SQL workbench."""

from flask import Flask, jsonify, render_template, request

from config import settings


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
        db_name = payload.get("db_name")
        if not db_name:
            return jsonify({"error": "db_name is required"}), 400
        return jsonify({"status": "scaffolded", "db_name": db_name})

    @app.errorhandler(503)
    def service_unavailable(error):
        return jsonify({"error": str(error), "hint": "Check Neo4j and LLM services."}), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
