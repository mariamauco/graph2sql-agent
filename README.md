# graph2sql-agent

Graph-assisted natural-language querying and database editing with SQLite,
Neo4j, OpenAI-compatible LLMs, Flask, and a small PHP frontend.

## Quick Start

From the repository root:

```bash
./scripts/setup_dev.sh
./scripts/select_spider_db.sh <database_name>
```

Then open `http://localhost:8080`.

`setup_dev.sh` creates `.venv`, installs the requirements, downloads the Spider
release into `data/spider_databases/`, and starts Docker Compose in the
background. `select_spider_db.sh` copies one Spider database to `data/`, which
is mounted directly into the agent container.

Before the first run, copy `.env.example` to `.env` and set your local Neo4j
password. Keep `.env` private.

## Running After Setup

After the initial setup, use the virtual environment when restarting the local
development stack:

```bash
source .venv/bin/activate
docker compose up --build -d
```


For direct Flask testing, open `http://localhost:5000/` or check
`http://localhost:5000/api/health`. The PHP frontend remains available at
`http://localhost:8080`.

Select a root `data/*.sqlite` source in the frontend and click **Build graph**.
The request travels through PHP to `POST /api/setup`; Flask extracts SQLite
metadata, builds Neo4j, and returns `nodes` and `edges` for force-graph.
Generated edit copies are stored under `data/working/` and are not listed as
source databases.

## Components

- **Neo4j:** Stores the schema knowledge graph.
- **OpenAI-compatible LLM:** Uses `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `LLM_MODEL` from `.env` for SQL generation and answer synthesis.
- **Flask agent:** Extracts database metadata, retrieves graph context, calls the LLM, and executes SQL.
- **PHP frontend:** Provides the browser UI and proxies requests to Flask.
- **`data/`:** Contains the downloaded Spider release and selected source SQLite databases; generated working copies live in `data/working/`.
- **Graph canvas:** `frontend/utils.js` renders the nodes and edges returned by the Flask setup endpoint with force-graph and handles browser API calls.
- **`scripts/`:** Contains setup, database selection, download, and benchmark commands.

## Useful Commands

```bash
docker compose ps
docker compose logs -f agent
docker compose down
docker compose down -v  # Also removes persistent volumes.
```
