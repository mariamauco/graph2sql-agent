# Knowledge-Graph Text-to-SQL & DB Mutation Agent

This document is the authoritative engineering guide for AI coding agents and developers working on this repository. Read and follow these specifications before creating or modifying any code.

## Current Implementation Status

This repository is currently a scaffold. The following features are **incomplete** and must not be treated as implemented:

- `services/graph/`: Neo4j HTTP access, graph construction, subgraph retrieval, aliases, and memory persistence are implemented; live Neo4j integration coverage remains to be expanded.
- `services/agent_service.py`: LLM provider calls, QA flow, and answer synteehsis are implemented. Edit flow, retries, telemetry, and graph synchronization are stubs.
- `app.py`: database listing, health, graph setup responses, working-graph file reuse, and QA are implemented; Edit endpoints are not implemented.
- `frontend/`: PHP setup, graph interaction, database selection, SQL results, and QA chat are implemented. Edit Mode view is implemented but does not work. telemetry views are incomplete.
- `scripts/run_benchmarks.py`: benchmark modes and evaluation metrics are not implemented.
- `scripts/tests/`: current tests only verifies graph QA flow.

---

## 1. Project Overview & Core Value Proposition

We are building an AI agent that performs natural language querying (**QA Mode**) and database/schema mutations (**Edit Mode**) over relational databases using a **Neo4j Knowledge Graph** accessed via HTTP.

### Why This Beats Raw Schema Prompting (The 5 Core Pillars)
Whenever you implement or modify `db_service.py`, `graph_build.py`, `graph_query.py`, or `agent_service.py`, you must preserve and reinforce these five mechanisms:

1. **Pre-Computed Shortest-Path `JOIN` Chains (`allShortestPaths`):**
   - Once anchor `:Table` nodes are matched from a user prompt, Neo4j runs Cypher `allShortestPaths` between those anchor tables (up to `k=5` matched tables) to automatically discover intermediate junction tables and outputs an **explicit, pre-verified `JOIN` path string** (e.g., `artists.id = albums.artist_id -> albums.id = tracks.album_id`).
2. **Safe Metadata & Distinct Value Profiling on `:Column` Nodes:**
   - During graph setup, the schema extractor inspects low-cardinality text/categorical columns ($\text{COUNT(DISTINCT col)} \le 10$) that do not match sensitive column names (e.g., `password`, `ssn`, `email`, `phone`, `secret`) and stores `distinct_values: ["COMP", "PEND", "CANC"]` directly on the `:Column` node in Neo4j.
3. **Full-Text Indexing + Semantic Aliasing:**
   - During setup, Neo4j builds a Full-Text Index (`schema_index`) across `Table` and `Column` nodes indexing `[n.name, n.aliases, n.sample_values]`. Normalized table/column aliases (e.g., snake_case split into words and domain synonyms) allow prompts like `"staff"` to match `emp_mstr_tbl`.
4. **Persistent Episodic Memory in Neo4j:**
   - **In QA Mode:** When a generated SQL query executes without error, persist a `(:VerifiedQuery {prompt, sql, created_at})-[:TOUCHES]->(:Table)` node in Neo4j. Subsequent queries touching those same `:Table` nodes retrieve 1–2 verified queries as few-shot examples.
   - **In Edit Mode:** When a user clarifies an implicit relationship missing from `PRAGMA foreign_key_list` or modifies schema structure, persist a `(:Table)-[:SEMANTIC_JOIN {join_condition, description}]->(:Table)` edge in Neo4j so the agent permanently remembers it across restarts.
5. **Safe Database & Graph Mutation (Edit Mode):**
   - Unlike stateless chat interfaces, this agent executes validated DML (`INSERT`, `UPDATE`, `DELETE`) and DDL (`ALTER TABLE`, `CREATE TABLE`) against a sandboxed working copy of the database and immediately synchronizes structural changes back into Neo4j.

---

## 2. System Architecture

All backend logic runs in a **single Python Flask server (`app.py`)** that communicates with local SQLite databases (or optional remote SQLAlchemy URIs), a Neo4j 5.x container over its **HTTP Query API v2**, and a configurable LLM provider.

```text
+-------------------------------------------------------------------------+
|                        Frontend Workbench UI                            |
|  - Setup Bar: Pick /data/*.sqlite (or Remote DB URI) -> [ Build Graph ] |
|  - Mode Toggle: [ QA Mode (Read) ]  |  [ Edit Mode (Write) ]            |
|  - Inspector: Natural Language Answer | Subgraph Used | Executed SQL    |
+------------------------------------+------------------------------------+
                                     | REST JSON
                                     v
+-------------------------------------------------------------------------+
|                        Single Flask Server (`app.py`)                   |
|                                                                         |
|  1. `db_service.py` (SQLite + SQLAlchemy Stretch Connector)             |
|     - Reads `/data/*.sqlite` via `PRAGMA table_info` & `foreign_key_list`|
|     - Executes Read SQL (QA Mode) & Write SQL on sandbox copy (Edit)    |
|                                                                         |
|  2. `services/graph/` (Neo4j HTTP Client and Graph Pipeline)             |
|     - Builds `:Database`, `:Table`, `:Column`, & `:FOREIGN_KEY` graph   |
|     - Runs Full-Text Search + `allShortestPaths` to extract subgraph    |
|     - Persists `:VerifiedQuery` & `:SEMANTIC_JOIN` edges                |
|                                                                         |
|  3. `agent_service.py` (QA & Edit Orchestrator + LangSmith Tracing)     |
|     - QA Flow:   Prompt -> Subgraph -> SQL -> Execute -> Answer + State |
|     - Edit Flow: Prompt -> Subgraph -> Write SQL -> Execute -> Sync     |
+------------------+-----------------------------------+------------------+
                   | HTTP POST                         | HTTPS / Local HTTP
                   | `/db/neo4j/query/v2`              | `/v1/chat/completions`
                   v                                   v
+------------------------------------+   +--------------------------------+
|   Neo4j 5.x (Docker or AuraDB)     |   |   LLM Engine (Configurable)    |
|   - Port 7474 (HTTP Query API v2)  |   |   - Default: OpenAI-compatible |
|   - Persistent Graph & Query Cache |   |     Luna (`gpt-6-luna`)            |
+------------------------------------+   +--------------------------------+
```

---

## 3. Target Repository Layout

Maintain this flat, modular project structure:

```text
.
├── AGENTS.md                  # Instructions for AI coding agents
├── plan.md                    # Architectural plan and motivation
├── docker-compose.yml         # Runs neo4j:5-community exposing HTTP port 7474
├── Dockerfile.agent           # sets up and runs flask app
├── .env.example               # Template environment variables
├── requirements.txt           # Python dependencies
├── app.py                     # Main Flask application & REST route definitions
├── config.py                  # Environment & model configuration loader
├── frontend/
│   ├── api.php                # Calls agent server
│   ├── index.php              # Runs frontend
│   ├── utils.js               # frontend behavior and force-graph rendering
│   ├── style.css              # style for frontend
│   └── Dockerfile             # exposes frontend port
├── services/
│   ├── __init__.py
│   ├── db_service.py          # SQLite PRAGMA extractor, sandbox manager, SQL executor
│   ├── graph/
│   │   ├── graph_client.py    # Neo4j HTTP Query API v2 client
│   │   ├── graph_build.py     # Graph nodes, relationships, and indexes
│   │   ├── graph_query.py     # Subgraph retrieval and query memory
│   └── agent_service.py       # LLM wrapper, QA pipeline, Edit pipeline
├── data/                      # Spider release and selected source DBs
│   └── spider_databases/      # Downloaded Spider dataset; keep runtime DBs at data/ root
│   └── working/                # Generated working database copies
└── scripts/
  ├── download_spider_data.sh # Downloads Spider dataset and databases
  ├── select_spider_db.sh
  ├── setup_dev.sh
  ├── run_benchmarks.py      # Automated Test A / Test B / Test C evaluation script
  └── results/               # Exported CSV/JSON metrics for RQ1-RQ4
```

---

## 4. Environment & Development Commands

### Environment Variables in `.env`

### Common Commands
- Startup services: `docker compose up --build`
- **Run services with  Container:** `docker compose up -d` 
- for using the configured cloud LLM, run `docker compose up -d`
- **Verify Neo4j HTTP Endpoint:** `curl -I http://localhost:7474`
- **Install Python Dependencies:** `pip install -r requirements.txt`
- **Run Flask Server:** `python app.py` (listens on `http://localhost:5000`)
- **Run Unit Tests:** `pytest scripts/tests/`
- **Run Benchmarks (A/B/C):** `python scripts/run_benchmarks.py --db concert_singer --limit 50`

---

## 5. Core Module Specifications & Implementation Rules

### 5.1 `services/db_service.py` (Database Connector & Sandbox)
**Implementation status: COMPLETE for local SQLite extraction, sandbox reset, and guarded read/write helpers.** Remote SQLAlchemy support remains a stretch goal.

1. **Never Corrupt Source `.sqlite` Files:**
  - Store the downloaded Spider release under `data/spider_databases/`, but copy selected original SQLite files to `data/{db_name}.sqlite` for runtime use.
  - On setup or before any Edit Mode operation, use `provide_working(db_path)` to create or return `data/working/{db_name}_working.sqlite`; pass `reset=True` when the working copy must be restored from the source.
  - Execute both QA and Edit queries against `data/working/{db_name}_working.sqlite` so newly inserted rows or altered columns in Edit Mode are immediately visible to follow-up QA Mode queries.
2. **Metadata Extraction (`extract_schema_metadata(db_name_or_uri)`):**
   - Query `sqlite_master` for all user tables (`type='table' AND name NOT LIKE 'sqlite_%'`).
   - Run `PRAGMA table_info('{table}')` to extract column `name`, `type`, `notnull`, `dflt_value`, and `pk`.
   - Run `PRAGMA foreign_key_list('{table}')` to extract `ref_table`, `from_col`, and `to_col`.
   - **Distinct Value Profiling:** For text/categorical columns (`TEXT`, `VARCHAR`, `CHAR`), if the column name does not match sensitive patterns (`password|secret|token|ssn|email|phone|address`), run:
     ```sql
     SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 11;
     ```
     If the returned count is between $1$ and $10$, attach those values as `sample_values` on the column metadata.
3. **Stretch Goal Hook (Remote DB URI):**
   - If `db_identifier` starts with `postgresql://`, `mysql://`, or `sqlite:///`, use `sqlalchemy.inspect(engine)` to produce the exact same metadata dictionary format as the local SQLite extractor.

---

### 5.2 `services/graph/` (Neo4j HTTP Query API v2 and Graph Pipeline)
**Implementation status: PARTIAL.** HTTP, graph setup, subgraph retrieval, and memory helpers are implemented; live Neo4j integration coverage and end-to-end agent use remain.

1. **Strict HTTP Requirement:**
   - Communicate with Neo4j **exclusively via HTTP POST** to `NEO4J_HTTP_URL` (`http://localhost:7474/db/neo4j/query/v2`) using `requests.post`. Do **not** require the `neo4j` binary Bolt Python driver.
   - Strip newlines or join multi-line Cypher strings with spaces before sending, and always pass dynamic values via the `"parameters"` dictionary (never string-interpolate user input into Cypher):
     ```python
     payload = {
         "statement": " ".join(cypher.splitlines()),
         "parameters": params or {}
     }
     ```
2. **Neo4j Graph Schema:**
   - **Nodes:**
     - `(:Database {name})`
     - `(:Table {id, db_name, name, aliases, row_count, ddl_summary})` where `id = f"{db_name}.{table_name}"`
     - `(:Column {id, db_name, table_name, name, data_type, is_pk, is_nullable, sample_values, aliases})` where `id = f"{db_name}.{table_name}.{col_name}"`
     - `(:VerifiedQuery {id, db_name, prompt, sql, created_at})`
   - **Relationships:**
     - `(:Database)-[:HAS_TABLE]->(:Table)`
     - `(:Table)-[:HAS_COLUMN]->(:Column)`
     - `(:Column)-[:FOREIGN_KEY {from_col, to_col}]->(:Column)`
     - `(:Table)-[:REFERENCES_TABLE {join_condition}]->(:Table)` *(Table-level shortcut edge with explicit join condition string like `"singer_in_concert.singer_id = singer.singer_id"`)*
     - `(:Table)-[:SEMANTIC_JOIN {join_condition, description, created_by}]->(:Table)` *(Created in Edit Mode)*
     - `(:VerifiedQuery)-[:TOUCHES]->(:Table)`
3. **Full-Text Index Creation:**
   - During setup, ensure the full-text index exists:
     ```cypher
     CREATE FULLTEXT INDEX schema_index IF NOT EXISTS
     FOR (n:Table|Column) ON EACH [n.name, n.aliases, n.sample_values]
     ```
4. **Subgraph Extraction Pipeline (`get_subgraph(db_name, prompt, k=5)`):**
   - **Step A (Anchor Discovery):** Tokenize `prompt` (removing stop words and escaping Lucene special characters) and query `db.index.fulltext.queryNodes("schema_index", $search_query)` filtered by `node.db_name = $db_name`. Map any matched `:Column` to its parent `:Table` and collect the top-$k$ anchor `:Table` nodes. Fallback to returning all tables in `db_name` if the database has $\le 5$ tables or if full-text search returns 0 hits.
   - **Step B (Shortest-Path Join Expansion):** Run Cypher `allShortestPaths` between all pairs of anchor tables across `[:REFERENCES_TABLE|SEMANTIC_JOIN*..3]` to pull in intermediate bridge tables and their `join_condition` properties.
   - **Step C (Context Assembly):** Fetch all `:Column` nodes for the resulting tables (including `sample_values` and `is_pk`) and up to 2 `:VerifiedQuery` nodes connected via `[:TOUCHES]`. Return a structured dictionary containing:
     - `tables`: List of table dicts with columns and sample values.
     - `join_paths`: List of explicit join condition strings (`"tableA.col = tableB.col"`).
     - `verified_queries`: Few-shot `prompt -> sql` examples.
     - `prompt_context_str`: A compact, LLM-ready formatted string of the subgraph.

---

### 5.3 `services/agent_service.py` (LLM Orchestrator for QA & Edit Flows)
**Implementation status: INCOMPLETE.** The rules below define the required behavior; the current module contains placeholders.

1. **Unified LLM Client:**
   - Use the `openai` Python SDK configured via `config.py`. The default provider is OpenAI-compatible Luna (`LLM_MODEL=gpt-6-luna`); omit `temperature` because Luna only supports its default value.
   - Record prompt tokens, completion tokens, and total latency (`time.perf_counter()`) on every request so the UI and benchmark runner always receive telemetry even if LangSmith is offline.
2. **Flow 1: Setup (`POST /api/setup`):**
   - `db_service.extract_schema_metadata(db_name)` $\rightarrow$ `graph_build.build_graph(db_name, metadata)` $\rightarrow$ return graph summary (`tables_count`, `columns_count`, `edges_count`, `status: "ready"`).
3. **Flow 2: QA Mode (`POST /api/agent/qa`):**
   - `prompt` $\rightarrow$ `subgraph = graph_query.get_subgraph(db_name, prompt, k=5)` $\rightarrow$ LLM generates a single SQLite `SELECT` query using `subgraph.prompt_context_str` $\rightarrow$ `db_service.execute_read_sql(db_name, sql)`.
   - **Self-Correction Retry:** If SQLite raises an `OperationalError` (e.g., `no such column` or syntax error), feed the failed SQL + SQLite error message + `subgraph.prompt_context_str` back to the LLM once to repair the query.
   - **Memory Persistence:** If execution succeeds, call `graph_query.save_verified_query(db_name, prompt, sql, touched_tables)`.
   - **Final Answer Construction:** Pass the user prompt + returned SQL rows (truncated to 50 rows max for prompt safety) to the LLM to synthesize a concise natural language answer; do not pass the SQL or graph context.
4. **Flow 3: Edit Mode (`POST /api/agent/edit`):**
   - `prompt` $\rightarrow$ `subgraph = graph_query.get_subgraph(db_name, prompt, k=5)` $\rightarrow$ LLM determines whether the user wants:
     - **Case A (Database DML/DDL Mutation):** Generates `INSERT`, `UPDATE`, `DELETE`, and `ALTER TABLE` SQL $\rightarrow$ executes via `db_service.execute_write_sql(db_name, sql)`. If the SQL contains `ALTER` or `DROP`, immediately re-run `extract_schema_metadata` and `build_graph` so Neo4j stays in sync.
     - **Case B (Semantic Graph Relationship Edit):** If the user states a domain relationship (e.g., *"Connect table X's `code` column to table Y's `ref_code` column"*), validate that both tables/columns exist and call `graph_query.add_semantic_join(db_name, from_table, to_table, join_condition, description)`.
   - Return a structured change report (`sql_executed`, `rows_affected`, `graph_updated`, `summary`).
---

### 5.4 Frontend
**Implementation status: PARTIAL.** The PHP/Apache shell and proxy exist, but the complete workbench workflow is not implemented.

1. **Stack:** Use PHP served by Apache with HTML, CSS, and browser JavaScript. Do not introduce React, TypeScript, Node.js services, or a frontend build pipeline.
2. **Files:** Keep the browser UI in `frontend/index.php`, browser behavior and graph rendering in `frontend/utils.js`, and styles in `frontend/style.css`. Keep backend proxying in `frontend/api.php`.
3. **Service boundary:** The browser calls `api.php`; `api.php` forwards approved requests to the Flask `agent` service using the Compose-injected `AGENT_URL`. Do not expose internal service hostnames or credentials to browser JavaScript.
4. **API proxy:** Keep the proxy limited to the documented Flask routes, preserve upstream status codes, return JSON errors for unavailable services, and avoid hard-coding environment-specific host ports.
5. **Container:** Build the frontend with `frontend/Dockerfile` from `php:8.3-apache`. The host-facing port is configured by `FRONTEND_PORT` in `.env`; Apache continues to use port `80` inside the container.
6. **Graph caching:** Store the selected graph response in browser `localStorage` for immediate repeat renders. Do not add a server-memory graph cache. The browser may receive the graph from the Flask setup response, which is backed by `data/working/{db_name}_graph.json` when that artifact already exists.

### 5.5 Docker Setup
**Implementation status: PARTIAL.** The Compose services, profiles, volumes, and development scripts exist, but successful container startup does not mean the agent behavior is complete.

1. **Compose services:** `docker-compose.yml` must manage `neo4j`, the optional Ollama compatibility profile, `agent` (Flask), and `frontend` (PHP/Apache).
2. **Build boundaries:** `Dockerfile.agent` installs Python dependencies from `requirements.txt` and runs Flask on internal port `5000`. The frontend image installs PHP/Apache. Do not require host Python, PHP, Neo4j, or Ollama installations for the Compose workflow.
3. **Environment:** Read credentials, provider selection, model name, host-facing ports, and telemetry settings from `.env`. Keep `.env` untracked and keep only safe placeholders in `.env.example`. Internal Compose ports and service URLs belong in Compose service configuration, not duplicated as environment variables.
4. **Dependencies:** Neo4j must be healthy before the agent starts. The default cloud provider uses `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `LLM_MODEL`; the optional `ollama` profile remains available for compatibility without being required.
5. **Persistent storage:** Preserve the named `neo4j_data` and `neo4j_logs` volumes; `ollama_data` is only used by the optional compatibility profile. Mount the repository `./data` directory directly at `/app/data` so selected SQLite files are immediately available to the agent. The host-facing Flask port is configured by `AGENT_PORT` and maps to the container's port `5000` for direct testing.
7. **Database data:** Source Spider `.sqlite` files must not be committed. Keep the downloaded release under `data/spider_databases/`, copy selected databases to `data/` root with `scripts/select_spider_db.sh`, and keep generated edit-mode working copies and graph artifacts under `data/working/`.
8. **Cache invalidation:** Any agent edit or schema rebuild must call `build_graph()`, which removes the matching `data/working/{db_name}_graph.json` before recomputing it. The frontend edit flow must also remove that database's `localStorage` graph entry.
9. **Required commands:** Validate with `docker compose config`, build with `docker compose build agent frontend`, start with `docker compose up -d`, inspect with `docker compose ps` and `docker compose logs`, and stop with `docker compose down`. Use `docker compose down -v` only when intentionally resetting persistent state.
10. **Provider switching:** Keep the LLM client behind the existing agent abstraction. The default `LLM_PROVIDER=openai` uses `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `LLM_MODEL` without the Ollama profile. `LLM_PROVIDER=ollama` remains supported through `docker compose --profile ollama up -d`; switching providers must not require changing Dockerfiles or frontend code.

---

## 6. Flask REST API Contracts (`app.py`)

Keep all endpoints returning consistent JSON payloads with proper HTTP status codes:

### `GET /api/databases`
Returns available `.sqlite` files in `/data`.
```json
{
  "databases": ["concert_singer", "chinook", "college_2"]
}
```

### `POST /api/setup`
Request:
```json
{
  "db_name": "concert_singer",
  "remote_uri": null,
  "reset_sandbox": false
}
```
Response:
```json
{
  "status": "ready",
  "db_name": "concert_singer",
  "tables_count": 4,
  "columns_count": 21,
  "foreign_keys_count": 2,
  "nodes": [],
  "edges": [],
  "cached": false,
  "latency_ms": 142.5
}
```

### `POST /api/agent/qa`
Request:
```json
{
  "db_name": "concert_singer",
  "prompt": "What are the names of singers who performed in a concert in 2014?",
  "mode": "test_c",
  "model": "qwen2.5-coder:7b"
}
```
Response:
```json
{
  "answer": "The singers who performed in a 2014 concert are Joe Sharp and Timbaland.",
  "sql": "SELECT DISTINCT T1.Name FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.Singer_ID = T2.Singer_ID JOIN concert AS T3 ON T2.concert_ID = T3.concert_ID WHERE T3.Year = '2014'",
  "rows": [{"Name": "Joe Sharp"}, {"Name": "Timbaland"}],
  "subgraph": {
    "tables": ["singer", "singer_in_concert", "concert"],
    "join_paths": [
      "singer_in_concert.Singer_ID = singer.Singer_ID",
      "singer_in_concert.concert_ID = concert.concert_ID"
    ],
    "verified_queries_used": 0
  },
  "telemetry": {
    "prompt_tokens": 310,
    "completion_tokens": 95,
    "total_tokens": 405,
    "graph_latency_ms": 8.4,
    "total_latency_ms": 1120.3,
    "retried": false
  }
}
```

### `POST /api/agent/edit`
Request:
```json
{
  "db_name": "concert_singer",
  "prompt": "Add a column phone_number TEXT to the singer table"
}
```
Response:
```json
{
  "summary": "Added column `phone_number` (TEXT) to table `singer` and synchronized the Neo4j schema graph.",
  "edit_type": "ddl",
  "sql": "ALTER TABLE singer ADD COLUMN phone_number TEXT;",
  "rows_affected": 0,
  "graph_synced": true,
  "subgraph": {
    "tables": ["singer"]
  },
  "telemetry": {
    "prompt_tokens": 240,
    "completion_tokens": 65,
    "total_latency_ms": 890.1
  }
}
```

---

## 7. Benchmarking & Evaluation Framework (`scripts/run_benchmarks.py`)

The benchmark script evaluates three modes across Spider benchmark questions and logs metrics for **RQ1 (Tokens)**, **RQ2 (Multi-table Join Execution Accuracy)**, and **RQ3 (Latency)**:

- **`test_a` (Baseline Raw Schema):** No Neo4j calls. Dumps the entire database DDL (`CREATE TABLE ...` for every table in the database) directly into the LLM prompt.
- **`test_b` (DB-Only Agent):** No Neo4j graph. The agent first calls a `list_tables` / `describe_tables` inspection step against SQLite before generating SQL.
- **`test_c` (Neo4j Graph-Assisted Agent):** Full pipeline using `graph_query.get_subgraph()` with Full-Text search, `allShortestPaths` join chains, column distinct value samples, and `:VerifiedQuery` few-shot memory.

**Execution Accuracy (EX) Rule:** Compare the result set of the generated SQL (`set(tuple(row) for row in pred_rows)`) against the ground-truth Spider SQL result set on the same `.sqlite` database.

---

## 8. Strict Guardrails for Coding Agents

1. **No Node.js Services:** Keep the backend 100% in Python (`Flask`). Do not scaffold Express/Node servers.
2. **No PostgreSQL Dependency Required for Local Dev:** Default to SQLite `.sqlite` files in `./data`. Only use SQLAlchemy for optional remote URIs.
3. **Always Use Neo4j HTTP Query API v2:** All Neo4j communication in `services/graph/graph_client.py` must go through HTTP `POST` to `/db/neo4j/query/v2` on port `7474`.
4. **Extract SQL Cleanly from LLM Responses:** Local models (`qwen2.5-coder:7b`) often wrap SQL in ` ```sql ... ``` ` markdown fences. Always strip markdown code fences before passing SQL to `sqlite3`.
5. **Graceful Degradation:** If Neo4j or the configured LLM is unreachable, return a clear JSON error message (`{"error": "...", "hint": "Run docker compose up -d"}`) with HTTP 503 rather than an unhandled stack trace.
