# graph2sql-agent

Graph-assisted natural-language querying and database editing with SQLite,
Neo4j, Ollama, Flask, and a small PHP frontend.

## Quick Start

From the repository root:

```bash
./scripts/setup_dev.sh
./scripts/select_spider_db.sh concert_singer
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
docker compose --profile ollama up #--build -d # to restart build
```


For direct Flask testing, open `http://localhost:5000/` or check
`http://localhost:5000/api/health`. The PHP frontend remains available at
`http://localhost:8080`.

## Components

- **Neo4j:** Stores the schema knowledge graph.
- **Ollama:** Runs the local LLM and stores models in the `ollama_data` volume.
- **Ollama profile:** Starts Ollama and downloads `LLM_MODEL`; omit the profile when using a cloud provider.
- **Flask agent:** Extracts database metadata, retrieves graph context, calls the LLM, and executes SQL.
- **PHP frontend:** Provides the browser UI and proxies requests to Flask.
- **`data/`:** Contains the downloaded Spider release plus selected runtime SQLite databases.
- **`scripts/`:** Contains setup, database selection, download, and benchmark commands.

## Useful Commands

```bash
docker compose ps
docker compose logs -f agent
docker compose down
docker compose down -v  # Also removes persistent volumes.
```
