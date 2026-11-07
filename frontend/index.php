<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Graph2SQL Agent</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://unpkg.com/force-graph"></script>
  <script src="utils.js" defer></script>
</head>
<body>
  <main class="shell">
    <header>
      <p class="eyebrow">Knowledge graph workbench</p>
      <h1>Graph2SQL Agent</h1>
      <p class="lede">Explore a database through natural language, with the schema graph close at hand.</p>
    </header>

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

    <div class="tab" role="tablist" aria-label="Agent mode">
      <button class="tablinks active" id="qa-tab" type="button" role="tab"
        aria-controls="qa-panel" aria-selected="true" data-panel="qa-panel">QA</button>
      <button class="tablinks" id="edit-tab" type="button" role="tab"
        aria-controls="edit-panel" aria-selected="false" data-panel="edit-panel">Edit</button>
    </div>

    <section id="qa-panel" class="panel agent-panel tabcontent" role="tabpanel" aria-labelledby="qa-tab">
      <div>
        <p class="eyebrow">QA mode</p>
        <h2>Ask about the selected database</h2>
      </div>
      <div id="qa-chat" class="chat-log" aria-live="polite">
        <p class="chat-empty">Ask a question to see the SQL result and answer.</p>
      </div>
      <form id="agent-form" class="agent-form">
        <label for="agent-prompt">Question</label>
        <div class="agent-input">
          <input id="agent-prompt" name="prompt" type="text" autocomplete="off"
            placeholder="Which records should I look at?" required>
          <button type="submit">Send</button>
        </div>
      </form>
    </section>

    <section id="edit-panel" class="panel agent-panel tabcontent" role="tabpanel"
      aria-labelledby="edit-tab" hidden>
      <div>
        <p class="eyebrow">Edit mode</p>
        <h2>Describe a database change</h2>
      </div>
      <div id="edit-chat" class="chat-log" aria-live="polite">
        <p class="chat-empty">Describe a change to see its result.</p>
      </div>
      <form id="edit-form" class="agent-form">
        <label for="edit-prompt">Change request</label>
        <div class="agent-input">
          <input id="edit-prompt" name="prompt" type="text" autocomplete="off"
            placeholder="Add a phone_number column to singer" required>
          <button type="submit">Send</button>
        </div>
      </form>
    </section>
  </main>
</body>
</html>
