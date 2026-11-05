<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Graph2SQL Agent</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://unpkg.com/force-graph"></script>
  <script src="graph.js" defer></script>
</head>
<body>
  <main class="shell">
    <header>
      <p class="eyebrow">Knowledge graph workbench</p>
      <h1>Graph2SQL Agent</h1>
      <p class="lede">Explore a database through natural language, with the schema graph close at hand.</p>
    </header>

    <!-- The browser talks to PHP; PHP forwards requests to Flask inside Compose. -->
    <section class="panel">
      <div class="controls">
        <div class="field">
          <label for="database">Database</label>
          <select id="database">
            <option value="">Loading databases...</option>
          </select>
        </div>
        <button id="setup" type="button">Build graph</button>
      </div>
      <div class="status-row">
        <p id="status" class="status" role="status">Checking the agent service...</p>
        <div class="legend" aria-label="Graph legend">
          <span><i class="swatch table-swatch"></i>Tables</span>
          <span><i class="swatch column-swatch"></i>Columns</span>
          <span><i class="swatch relation-swatch"></i>Relations</span>
        </div>
      </div>
      <div id="graph" aria-label="Database schema graph"></div>
    </section>
  </main>
  <script>
    // Keep API calls here; force-graph rendering lives in graph.js.
    const database = document.querySelector('#database');
    const status = document.querySelector('#status');

    function cacheKey() {
      return `graph2sql:${database.value}`;
    }

    function showCachedGraph() {
      if (!database.value) return false;
      const saved = localStorage.getItem(cacheKey());
      if (!saved) return false;
      try {
        renderGraph(JSON.parse(saved));
        status.textContent = 'ready';
        return true;
      } catch (error) {
        localStorage.removeItem(cacheKey());
        return false;
      }
    }

    async function readJson(response) {
      const text = await response.text();
      try {
        return JSON.parse(text);
      } catch (error) {
        return {error: `Agent returned a non-JSON response (${response.status}).`};
      }
    }

    async function loadDatabases() {
      try {
        const response = await fetch('api.php?action=databases');
        const data = await readJson(response);
        database.replaceChildren(...(data.databases || []).map((name) => {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          return option;
        }));
        status.textContent = response.ok ? 'Agent service is ready.' : (data.error || 'Unable to load databases.');
        showCachedGraph();
      } catch (error) {
        status.textContent = 'The agent service is unavailable.';
      }
    }

    document.querySelector('#setup').addEventListener('click', async () => {
      if (!database.value) return;
      if (showCachedGraph()) return;
      status.textContent = 'Building the schema graph...';
      const response = await fetch('api.php?action=setup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({db_name: database.value})
      });
      const data = await readJson(response);
      status.textContent = data.status || data.error || 'Setup finished.';
      if (response.ok) {
        localStorage.setItem(cacheKey(), JSON.stringify(data));
        renderGraph(data);
      }
    });

    loadDatabases();
  </script>
</body>
</html>
