<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Graph2SQL Agent</title>
  <link rel="stylesheet" href="style.css">
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
      <div class="field">
        <label for="database">Database</label>
        <select id="database">
          <option value="">Loading databases...</option>
        </select>
      </div>
      <button id="setup" type="button">Build graph</button>
      <p id="status" class="status" role="status">Checking the agent service...</p>
    </section>
  </main>
  <script>
      // Keep browser code small; backend routing stays in api.php.
    const database = document.querySelector('#database');
    const status = document.querySelector('#status');

    async function loadDatabases() {
      try {
        const response = await fetch('api.php?action=databases');
        const data = await response.json();
        database.replaceChildren(...(data.databases || []).map((name) => {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          return option;
        }));
        status.textContent = response.ok ? 'Agent service is ready.' : (data.error || 'Unable to load databases.');
      } catch (error) {
        status.textContent = 'The agent service is unavailable.';
      }
    }

    document.querySelector('#setup').addEventListener('click', async () => {
      if (!database.value) return;
      status.textContent = 'Building the schema graph...';
      const response = await fetch('api.php?action=setup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({db_name: database.value})
      });
      const data = await response.json();
      status.textContent = data.status || data.error || 'Setup finished.';
    });

    loadDatabases();
  </script>
</body>
</html>
