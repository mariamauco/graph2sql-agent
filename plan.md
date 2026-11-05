# Graph2SQL Agent Plan

## issue 1 - set up project
Set up the Flask application and multi-service `docker-compose.yml` for Neo4j, Ollama, the agent, and the PHP frontend. Host ports are configured through `.env`; the repository `data/` directory is bind-mounted into the agent container.
    
- **Acceptance Criteria:**
    - [x] `docker-compose.yml` runs services and persistent volumes.
    - [x] Store the downloaded Spider release under `data/spider_databases/`, copy selected runtime databases to the `data/` root, and keep working copies in `data/working/`.
    - [ ] Implement `db_service.py` with:
        - `extract_schema(db_path)`: Extracts tables (`sqlite_master`), columns/types/PKs (`PRAGMA table_info`), foreign keys (`PRAGMA foreign_key_list`), table row counts, and safe low-cardinality sample values.
        - `execute_read_sql(db_path, sql)`: Runs read-only `SELECT` queries with a timeout.
        - `provide_working(db_path, reset=False)`: Creates or returns `data/working/{db_name}_working.sqlite`; `reset=True` restores it from the original source.
        - `execute_write_sql(db_path, sql)`: Runs `INSERT`/`UPDATE`/`DELETE`/`ALTER` on the working copy so original benchmark files aren't corrupted.
        - _(Stretch Hook)_ Accept an optional SQLAlchemy URI (`postgresql://...` or `mysql://...`) in `db_service.py` so a remotely hosted DB can be added from the UI later.

## issue 2 - setup flow
Implement the **Setup Flow** (`use a db schema --> create graph --> ready`) and the subgraph retrieval logic over Neo4j's HTTP Query API v2 (`/db/neo4j/query/v2`).
    
- **Acceptance Criteria:**
    - [ ] Implement `run_cypher_http()` helper in `graph_client.py` communicating with Neo4j via HTTP `POST`.
    - [ ] Implement `build_graph(db_name, schema_metadata)`: Creates `:Table` and `:Column` nodes (with data types, PK flags, aliases, and sample categorical values) and `:HAS_COLUMN` / `:FOREIGN_KEY` edges in Neo4j, plus a Full-Text search index.
    - [ ] Implement `get_subgraph(db_name, user_prompt, k=5)`:
        1. Queries the Neo4j Full-Text index using keywords from `user_prompt` to locate top-$k$ anchor `:Table` nodes.
        2. Runs `allShortestPaths` Cypher traversal between anchor tables (up to 3 hops) to automatically pull in intermediate junction tables and explicit `JOIN` conditions.
        3. Fetches any `:VerifiedQuery` nodes linked to those tables for few-shot grounding.
    - [ ] Expose `POST /api/setup` in Flask (`{"db_name": "concert_singer.sqlite"}` $\rightarrow$ returns node/edge counts and `status: "ready"`).

## issue 3 - qa mode flow
Implement the **QA Mode Flow** (`prompt --> add graph state --> create sql --> execute sql --> use data returned + graph state when constructing response`) with configurable LLM support (local Ollama or GPT-4o).
    
- **Acceptance Criteria:**
    - [ ] Configure LLM client wrapper supporting both local Ollama (`qwen2.5-coder:7b`) and OpenAI (`gpt-4o` / `gpt-4o-mini`).
    - [ ] Build `run_qa_flow(db_name, prompt)`:
        1. Calls `graph_query.get_subgraph(db_name, prompt, k=5)` to get pruned tables, columns, sample values, and pre-computed `JOIN` paths.
        2. Prompts the LLM with the subgraph state to generate an executable SQLite `SELECT` query.
        3. Calls `db_service.execute_read_sql()` (with 1 automatic self-correction retry if SQLite returns a syntax/column error).
        4. Stores successful query as a `:VerifiedQuery` node in Neo4j for persistent learning.
        5. Passes the **returned SQL data** to the LLM to synthesize the final natural language response.
    - [ ] Expose via `POST /api/agent/qa`.

## issue 4 - edit mode flow
Implement the **Edit Mode Flow** (`prompt --> add graph state --> create sql code --> execute --> report changes`) and keep the Neo4j graph synchronized with any schema or relationship edits.
- **Acceptance Criteria:
    - [ ] Build `run_edit_flow(db_name, prompt)`:
        1. Retrieves the target tables' subgraph state from Neo4j (including PK/FK constraints so mutations don't violate integrity).
        2. Generates the mutating SQL (`INSERT`, `UPDATE`, `DELETE`, `ALTER TABLE`, `CREATE TABLE`) or custom graph relationship command.
        3. Executes the SQL via `db_service.execute_write_sql()`.
        4. **Graph Persistence Sync:** If the edit modified table structure (`ALTER`/`CREATE`/`DROP`) or defined a new semantic relationship between tables, updates the Neo4j nodes/edges via HTTP API.
        5. Returns a structured change report detailing the executed SQL, rows affected, and updated graph state.
    - [ ] Expose via `POST /api/agent/edit`.

## issue 5 - frontend ui for setup and modes
Build a clean web UI to initialize databases, run QA and Edit prompts, and inspect the Neo4j subgraph state alongside the SQL execution results.
    
- **Acceptance Criteria:**
    - [ ] **Setup Header:** Dropdown listing `/data/*.sqlite` files (plus an input field for a remote DB connection URI for the stretch goal) and a **"Setup Graph"** button displaying `"Ready (X Tables, Y Edges)"`.
    - [ ] **Mode & Model Controls:** Toggle between **QA Mode** and **Edit Mode**, and select between Local LLM (Ollama) and Cloud LLM (GPT-4o).
    - [ ] **Main Workspace:** Chat interface displaying the natural language answer/change report, alongside an inspector panel showing:
        1. The extracted **Neo4j Subgraph** (tables, columns, and shortest-path joins used).
        2. The **Generated SQL** and **Returned Data Table / Affected Rows**.
        3. **Telemetry Badges:** Prompt tokens used and response latency.

## issue 6 - ABC benchmark
Quantify how the Neo4j Graph-Assisted pipeline outperforms raw full-schema prompting across Spider benchmark databases using LangSmith telemetry.
    
- **Acceptance Criteria:**
    - [ ] Implement automated runner comparing:
        - **Test A (Baseline - Raw ChatGPT):** Passes the entire raw SQLite DDL schema in the prompt with no Neo4j graph.
        - **Test B (DB-Only Agent):** Agent inspects SQLite directly via tool calls without Neo4j pathfinding.
        - **Test C (Neo4j Graph-Assisted Agent):** Uses `graph_query.get_subgraph()` with shortest-path `JOIN` hints, value profiling, and persistent query memory.
    - [ ] Log Prompt Tokens (**RQ1**), Multi-Table Join Execution Accuracy (**RQ2**), and End-to-End Latency (**RQ3**) via LangSmith (`LANGCHAIN_TRACING_V2=true`) and export a comparative CSV/chart for the final paper.