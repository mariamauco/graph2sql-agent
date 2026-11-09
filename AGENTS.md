# Knowledge-Graph Text-to-SQL & DB Mutation Agent

This document is the authoritative engineering guide for AI coding agents and developers working on this repository. Read and follow these specifications before creating or modifying any code.

## Current Implementation Status

The repository has working graph-assisted QA and confirmation-based edit flows, plus a PHP/JavaScript frontend. Coverage and some planned features remain incomplete:

- `services/graph/`: Neo4j HTTP access, graph construction and refresh, subgraph retrieval, aliases, and query memory are implemented; live integration coverage remains limited.
- `services/agent_service.py`: QA, edit proposal generation, confirmation-based edit execution, semantic joins, and schema graph refresh are implemented; telemetry is limited to elapsed time and retry status for QA.
- `app.py`: database listing, health, graph setup, working-copy reset, QA, edit proposal, and edit acceptance endpoints are implemented.
- `frontend/`: database selection, graph build and reset, graph rendering, QA chat, and edit proposal/acceptance UI are implemented. There is no discard endpoint; the UI exposes acceptance for a pending proposal.
- `scripts/run_benchmarks.py`: benchmark modes and evaluation metrics are not implemented.
- `scripts/tests/`: includes graph QA exploration and a college_1 edit-flow check; live Neo4j and LLM services are needed to run them.

---

## 1. Project Overview & Core Value Proposition

We are building an AI agent that performs natural language querying (**QA Mode**) and database/schema mutations (**Edit Mode**) over relational databases using a **Neo4j Knowledge Graph** accessed via HTTP.

### Why This Beats Raw Schema Prompting (The 5 Core Pillars)
Whenever you implement or modify `db_service.py`, `graph_build.py`, `graph_query.py`, or `agent_service.py`, you must preserve and reinforce these five mechanisms:

1. **Pre-Computed Shortest-Path `JOIN` Chains (`allShortestPaths`):**
   - Once anchor `:Table` nodes are matched from a user prompt, Neo4j runs Cypher `allShortestPaths` between those anchor tables (up to `k=5` matched tables) to automatically discover intermediate junction tables and outputs an **explicit, pre-verified `JOIN` path string** (e.g., `artists.id = albums.artist_id -> albums.id = tracks.album_id`).
2. **Safe Metadata & Distinct Value Profiling on `:Column` Nodes:**
   - During graph setup, the schema extractor inspects low-cardinality text/categorical columns ($\text{COUNT(DISTINCT col)} \le 10$) that do not match sensitive column names (e.g., `password`, `ssn`, `email`, `phone`, `secret`) and stores safe values in the `sample_values` property on `:Column` nodes in Neo4j.
3. **Full-Text Indexing + Semantic Aliasing:**
   - During setup, Neo4j builds a Full-Text Index (`schema_index`) across `Table` and `Column` nodes indexing `[n.name, n.aliases, n.sample_values]`. Normalized table/column aliases (e.g., snake_case split into words and domain synonyms) allow prompts like `"staff"` to match `emp_mstr_tbl`.
4. **Persistent Episodic Memory in Neo4j:**
   - **In QA Mode:** When a generated SQL query executes without error, persist a `(:VerifiedQuery {prompt, sql, created_at})-[:TOUCHES]->(:Table)` node in Neo4j. Subsequent queries touching those same `:Table` nodes retrieve 1–2 verified queries as few-shot examples.
   - **In Edit Mode:** When a user clarifies an implicit relationship missing from `PRAGMA foreign_key_list` or modifies schema structure, persist a `(:Table)-[:SEMANTIC_JOIN {join_condition, description}]->(:Table)` edge in Neo4j so the agent permanently remembers it across restarts.
5. **Safe Database & Graph Mutation (Edit Mode):**
   - Unlike stateless chat interfaces, this agent executes supported DML (`INSERT`, `UPDATE`, `DELETE`) and table DDL (`ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`) against a sandboxed working copy and synchronizes structural changes to Neo4j.

---

## 2. System Architecture

All backend logic runs in a **single Python Flask server (`app.py`)** that communicates with local SQLite databases (or optional remote SQLAlchemy URIs), a Neo4j 5.x container over its **HTTP Query API v2**, and a configurable LLM provider.

```text
+-------------------------------------------------------------------------+
|                        Frontend Workbench UI                            |
|  - Database: Pick /data/*.sqlite -> [ Build Graph ] [ Reset Database ]  |
|  - Tabs: [ QA Mode (Read) ] | [ Edit Mode (Propose / Accept) ]         |
+------------------------------------+------------------------------------+
                                     | REST JSON
                                     v
+-------------------------------------------------------------------------+
|                        Single Flask Server (`app.py`)                   |
|                                                                         |
|  1. `db_service.py` (SQLite + SQLAlchemy Stretch Connector)             |
|     - Reads SQLite via `PRAGMA table_info` & `foreign_key_list`          |
|     - Executes Read SQL (QA Mode) & Write SQL on sandbox copy (Edit)    |
|                                                                         |
|  2. `services/graph/` (Neo4j HTTP Client and Graph Pipeline)             |
|     - Builds `:Database`, `:Table`, `:Column`, & `:FOREIGN_KEY` graph   |
|     - Runs Full-Text Search + `allShortestPaths` to extract subgraph    |
|     - Persists `:VerifiedQuery` & `:SEMANTIC_JOIN` edges                |
|                                                                         |
|  3. `agent_service.py` (QA & Edit Orchestrator)                         |
|     - QA Flow:   Prompt -> Subgraph -> SQL -> Execute -> Answer + State |
|     - Edit Flow: Prompt -> Proposal -> Accept -> Execute -> Sync        |
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
- **Run graph QA exploration:** `python scripts/tests/test_graph_query.py --index 0`
- **Run edit-flow check:** `python scripts/tests/test_graph_edit.py` (uses `college_1.sqlite`; requires the configured LLM and live Neo4j services)
- **Run Benchmarks (A/B/C):** `python scripts/run_benchmarks.py --db concert_singer --limit 50`

---

## 5. Core Module Specifications & Implementation Rules

### 5.1 `services/db_service.py` (Database Connector & Sandbox)
**Implementation status: COMPLETE for local SQLite extraction, sandbox reset, and guarded read/write helpers.** Remote SQLAlchemy support remains a stretch goal.

1. **Never Corrupt Source `.sqlite` Files:**
  - Store the downloaded Spider release under `data/spider_databases/`, but copy selected original SQLite files to `data/{db_name}.sqlite` for runtime use.
  - `provide_working(db_path, reset=False)` creates or returns `data/working/{db_name}_working.sqlite`; pass `reset=True` to replace it from the source. `/api/reset` does this and clears the server graph artifact before the frontend rebuilds the graph.
  - Execute both QA and Edit queries against `data/working/{db_name}_working.sqlite` so Edit Mode changes are visible to follow-up QA queries.
2. **Metadata Extraction (`extract_schema(db_path)`):**
   - Query `sqlite_master` for all user tables (`type='table' AND name NOT LIKE 'sqlite_%'`).
   - Run `PRAGMA table_info('{table}')` to extract column `name`, `type`, `notnull`, `dflt_value`, and `pk`.
   - Run `PRAGMA foreign_key_list('{table}')` to extract `ref_table`, `from_col`, and `to_col`.
   - **Safe Sample Profiling:** For text/categorical columns (`TEXT`, `VARCHAR`, `CHAR`), if the column name does not match sensitive patterns (`password|secret|token|ssn|email|phone|address`), run:
     ```sql
     SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 11;
     ```
     If the returned count is between $1$ and $10$, attach those values as `sample_values` on the column metadata.
   - For date/time columns (by declared type or column name), inspect up to 20 non-null values and store a recognized compact `date_format` on the column metadata. Include this hint in the LLM context only for date-related questions.
3. **Stretch Goal Hook (Remote DB URI):**
   - If `db_identifier` starts with `postgresql://`, `mysql://`, or `sqlite:///`, use `sqlalchemy.inspect(engine)` to produce the exact same metadata dictionary format as the local SQLite extractor.

---

### 5.2 `services/graph/` (Neo4j HTTP Query API v2 and Graph Pipeline)
**Implementation status: IMPLEMENTED; integration coverage remains limited.** HTTP, graph setup and refresh, subgraph retrieval, and memory helpers are used by the Flask flows.

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
     - `(:Column {id, db_name, table_name, name, data_type, is_pk, is_nullable, sample_values, aliases, date_format})` where `id = f"{db_name}.{table_name}.{col_name}"`
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
   - **Step B (Shortest-Path Join Expansion):** Run Cypher `allShortestPaths` between anchor table pairs across `[:REFERENCES_TABLE|SEMANTIC_JOIN*..3]`. Include every table ID on each returned path in the table-context lookup, so intermediate bridge tables and their columns appear in `subgraph["tables"]`; retain explicit relationship join conditions in `subgraph["join_paths"]`.
   - **Step C (Context Assembly):** Fetch all `:Column` nodes for the resulting tables (including `sample_values` and `is_pk`) and up to 2 `:VerifiedQuery` nodes connected via `[:TOUCHES]`. Return a structured dictionary containing:
     - `tables`: List of table dicts with columns and sample values.
     - `join_paths`: List of explicit join condition strings (`"tableA.col = tableB.col"`).
     - `verified_queries`: Few-shot `prompt -> sql` examples.
     - `prompt_context_str`: A compact, LLM-ready formatted string of the subgraph.

---

### 5.3 `services/agent_service.py` (LLM Orchestrator for QA & Edit Flows)
**Implementation status: IMPLEMENTED; telemetry and integration coverage are limited.** QA and confirmation-based Edit flows share the graph context and SQL-generation helpers.

1. **Unified LLM Client:**
   - Use the `openai` Python SDK configured via `config.py`. The default provider is OpenAI-compatible Luna (`LLM_MODEL=gpt-6-luna`); omit `temperature` because Luna only supports its default value.
   - QA telemetry reports total latency, retry status, and aggregated prompt/completion/total tokens from its model calls. Edit proposal telemetry reports the same token totals. Counts depend on the configured provider returning usage data; LangSmith tracing is not used.
2. **Flow 1: Setup (`POST /api/setup`):**
   - Resolve the source SQLite file, call `graph_build.refresh_graph_from_db(db_name, db_path)` to read the working copy and synchronize Neo4j, then return graph elements and a schema summary. A cached graph artifact may be returned when present.
3. **Flow 2: QA Mode (`POST /api/agent/qa`):**
   - `prompt` $\rightarrow$ `subgraph = graph_query.get_subgraph(db_name, prompt)` $\rightarrow$ LLM generates a single SQLite `SELECT` query using `subgraph.prompt_context_str` $\rightarrow$ `db_service.execute_read_sql(db_path, sql)` against the working copy.
   - **Self-Correction Retry:** If SQLite raises an `OperationalError` (e.g., `no such column` or syntax error), feed the failed SQL + SQLite error message + `subgraph.prompt_context_str` back to the LLM once to repair the query.
   - **Memory Persistence:** If execution succeeds, call `graph_query.save_verified_query(db_name, prompt, sql, touched_tables)`.
   - **Final Answer Construction:** Pass the user prompt + returned SQL rows (truncated to 50 rows max for prompt safety) to the LLM to synthesize a concise natural language answer; do not pass the SQL or graph context.
4. **Flow 3: Edit Mode (`POST /api/agent/edit` and `/api/agent/edit/accept`):**
   - `run_edit_flow()` calls `graph_query.get_subgraph()`, asks the LLM for one SQL edit or semantic-join plan, explains the plan, and keeps the single pending plan in process memory. It does not mutate the database or graph.
   - On explicit acceptance, `apply_edit()` executes `INSERT`, `UPDATE`, `DELETE`, `ALTER TABLE`, `CREATE TABLE`, or `DROP TABLE` on the working copy. DML reports affected rows. DDL calls `refresh_graph_from_db()` to re-extract metadata and reconcile Neo4j.
   - For a semantic-join plan, call `graph_query.add_semantic_join()`.
   - Return the SQL or relationship, rows affected, summary, and graph synchronization status.
---

### 5.4 Frontend
**Implementation status: IMPLEMENTED for the current workbench flows.** The PHP/Apache frontend supports database selection, graph build/reset, QA, and edit proposal/acceptance. It does not provide telemetry views or a proposal discard endpoint.

1. **Stack:** Use PHP served by Apache with HTML, CSS, and browser JavaScript. Do not introduce React, TypeScript, Node.js services, or a frontend build pipeline.
2. **Files:** Keep the browser UI in `frontend/index.php`, browser behavior and graph rendering in `frontend/utils.js`, and styles in `frontend/style.css`. Keep backend proxying in `frontend/api.php`.
3. **Service boundary:** The browser calls `api.php`; `api.php` forwards approved requests to the Flask `agent` service using the Compose-injected `AGENT_URL`. Do not expose internal service hostnames or credentials to browser JavaScript.
4. **API proxy:** Keep the proxy limited to the documented Flask routes, preserve upstream status codes, return JSON errors for unavailable services, and avoid hard-coding environment-specific host ports.
5. **Container:** Build the frontend with `frontend/Dockerfile` from `php:8.3-apache`. The host-facing port is configured by `FRONTEND_PORT` in `.env`; Apache continues to use port `80` inside the container.
6. **Graph caching:** Store the selected graph response in browser `localStorage` for immediate repeat renders. Do not add a server-memory graph cache. The browser may receive the graph from the Flask setup response, which is backed by `data/working/{db_name}_graph.json` when that artifact already exists.
7. **Edit and reset UI:** Keep QA and Edit in tabs with separate chat logs. After an accepted edit, rebuild and render the graph through `POST /api/setup`. The Reset Database button calls `POST /api/reset`, then rebuilds the graph so both the displayed graph and caches reflect the restored working copy.

### 5.5 Docker Setup
**Implementation status: PARTIAL.** The Compose services, profiles, volumes, and development scripts exist, but successful container startup does not mean the agent behavior is complete.

1. **Compose services:** `docker-compose.yml` must manage `neo4j`, the optional Ollama compatibility profile, `agent` (Flask), and `frontend` (PHP/Apache).
2. **Build boundaries:** `Dockerfile.agent` installs Python dependencies from `requirements.txt` and runs Flask on internal port `5000`. The frontend image installs PHP/Apache. Do not require host Python, PHP, Neo4j, or Ollama installations for the Compose workflow.
3. **Environment:** Read credentials, provider selection, model name, host-facing ports, and telemetry settings from `.env`. Keep `.env` untracked and keep only safe placeholders in `.env.example`. Internal Compose ports and service URLs belong in Compose service configuration, not duplicated as environment variables.
4. **Dependencies:** Neo4j must be healthy before the agent starts. The default cloud provider uses `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `LLM_MODEL`; the optional `ollama` profile remains available for compatibility without being required.
5. **Persistent storage:** Preserve the named `neo4j_data` and `neo4j_logs` volumes; `ollama_data` is only used by the optional compatibility profile. Mount the repository `./data` directory directly at `/app/data` so selected SQLite files are immediately available to the agent. The host-facing Flask port is configured by `AGENT_PORT` and maps to the container's port `5000` for direct testing.
7. **Database data:** Source Spider `.sqlite` files must not be committed. Keep the downloaded release under `data/spider_databases/`, copy selected databases to `data/` root with `scripts/select_spider_db.sh`, and keep generated edit-mode working copies and graph artifacts under `data/working/`.
8. **Cache invalidation:** `graph_build.build_graph()` removes the matching `data/working/{db_name}_graph.json` before recomputing it. `/api/reset` also removes that artifact after restoring the working copy. After accepted edits or resets, the frontend replaces that database's `localStorage` graph entry with the rebuilt response; on rebuild failure it clears the stale entry.
9. **Required commands:** Validate with `docker compose config`, build with `docker compose build agent frontend`, start with `docker compose up -d`, inspect with `docker compose ps` and `docker compose logs`, and stop with `docker compose down`. Use `docker compose down -v` only when intentionally resetting persistent state.
10. **Provider switching:** Keep the LLM client behind the existing agent abstraction. `LLM_PROVIDER=openai` uses `OPENAI_BASE_URL` and `OPENAI_API_KEY`; `LLM_PROVIDER=claude` uses `ANTHROPIC_API_KEY`; and `LLM_PROVIDER=gemini` uses `GEMINI_API_KEY` through Google's OpenAI-compatible endpoint. Each provider has a default model when `LLM_MODEL` is unset. `LLM_PROVIDER=ollama` remains supported through `docker compose --profile ollama up -d`; switching providers must not require changing Dockerfiles or frontend code.

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
{"db_name": "concert_singer"}
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
  "cached": false
}
```

### `POST /api/reset`
Restores the selected database's working copy from its source and invalidates the server-side graph artifact. The frontend follows with `POST /api/setup` to rebuild and display the graph.

Request:
```json
{"db_name": "college_1"}
```
Response:
```json
{"status": "working database reset"}
```

### `POST /api/agent/qa`
Request:
```json
{
  "db_name": "concert_singer",
  "prompt": "What are the names of singers who performed in a concert in 2014?"
}
```
Response:
```json
{
  "answer": "The singers who performed in a 2014 concert are Joe Sharp and Timbaland.",
  "sql": "SELECT DISTINCT T1.Name FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.Singer_ID = T2.Singer_ID JOIN concert AS T3 ON T2.concert_ID = T3.concert_ID WHERE T3.Year = '2014'",
  "rows": [{"Name": "Joe Sharp"}, {"Name": "Timbaland"}],
  "subgraph": {"tables": [], "join_paths": [], "verified_queries": [], "prompt_context_str": "..."},
  "telemetry": {"total_latency_ms": 1120.3, "retried": false}
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
  "status": "awaiting_confirmation",
  "kind": "sql",
  "summary": "Add phone_number to singer.",
  "plan_summary": "Add a nullable phone_number column to singer.",
  "sql": "ALTER TABLE singer ADD COLUMN phone_number TEXT;",
  "subgraph": {"tables": []}
}
```

The proposal does not mutate the database. Apply it only after user confirmation:

### `POST /api/agent/edit/accept`
Request:
```json
{"db_name": "concert_singer"}
```

The response reports `status`, `kind`, `summary`, `sql`, `rows_affected`,
`graph_updated`, and for schema edits the refreshed graph summary. After an
accepted edit, the frontend calls `/api/setup` to refresh the graph it displays
and caches.

---

## 7. Benchmarking & Evaluation Framework (`scripts/run_benchmarks.py`)

The benchmark script evaluates three modes across Spider benchmark questions and logs metrics for **RQ1 (Tokens)**, **RQ2 (Multi-table Join Execution Accuracy)**, and **RQ3 (Latency)**:

- **`test_a` (Baseline Raw Schema):** No Neo4j calls. Dumps the entire database DDL (`CREATE TABLE ...` for every table in the database) directly into the LLM prompt.
- **`test_b` (DB-Only Agent):** No Neo4j graph. The agent first calls a `list_tables` / `describe_tables` inspection step against SQLite before generating SQL.
- **`test_c` (Neo4j Graph-Assisted Agent):** Full pipeline using `graph_query.get_subgraph()` with Full-Text search, `allShortestPaths` join chains, column distinct value samples, and `:VerifiedQuery` few-shot memory.

**Execution Accuracy (EX) Rule:** Compare unordered result sets on the same `.sqlite` database. For a gold query that groups rows and uses `ORDER BY COUNT(*) LIMIT 1`, treat all groups tied for the best count as acceptable, since SQLite may return any one of them without a tie-breaker.

---

## 8. Strict Guardrails for Coding Agents

1. **No Node.js Services:** Keep the backend 100% in Python (`Flask`). Do not scaffold Express/Node servers.
2. **No PostgreSQL Dependency Required for Local Dev:** Default to SQLite `.sqlite` files in `./data`. Only use SQLAlchemy for optional remote URIs.
3. **Always Use Neo4j HTTP Query API v2:** All Neo4j communication in `services/graph/graph_client.py` must go through HTTP `POST` to `/db/neo4j/query/v2` on port `7474`.
4. **Extract SQL Cleanly from LLM Responses:** Local models (`qwen2.5-coder:7b`) often wrap SQL in ` ```sql ... ``` ` markdown fences. Always strip markdown code fences before passing SQL to `sqlite3`.
5. **Graceful Degradation:** If Neo4j or the configured LLM is unreachable, return a clear JSON error message (`{"error": "...", "hint": "Run docker compose up -d"}`) with HTTP 503 rather than an unhandled stack trace.
