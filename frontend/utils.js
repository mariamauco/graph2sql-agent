const database = document.querySelector('#database');
const status = document.querySelector('#status');
const qaChat = document.querySelector('#qa-chat');
const promptInput = document.querySelector('#agent-prompt');
let graph;

async function readJson(response) {
  try {
    return JSON.parse(await response.text());
  } catch {
    return {error: `Agent returned a non-JSON response (${response.status}).`};
  }
}

function renderGraph(data) {
  const container = document.querySelector('#graph');
  const nodes = (data.nodes || []).map(node => node.data || node);
  const links = (data.edges || []).map(edge => edge.data || edge);
  graph?._destructor?.();
  container.replaceChildren();
  graph = ForceGraph()(container)
    .graphData({nodes, links})
    .nodeId('id')
    .nodeLabel(node => node.label || node.id)
    .nodeColor(node => node.type === 'table' ? '#c85c35' : '#3d6fa3')
    .nodeRelSize(5)
    .linkLabel(link => link.label || link.type || '')
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(1)
    .linkColor(() => '#4f8f64')
    .width(container.clientWidth)
    .height(container.clientHeight);
}

function showCachedGraph() {
  const key = `graph2sql:${database.value}`;
  const saved = localStorage.getItem(key);
  if (!saved) return false;
  try {
    renderGraph(JSON.parse(saved));
    status.textContent = 'ready';
    return true;
  } catch {
    localStorage.removeItem(key);
    return false;
  }
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  return {response, data: await readJson(response)};
}

function addDetails(entry, label, data) {
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  const content = document.createElement('pre');
  summary.textContent = label;
  content.textContent = JSON.stringify(data, null, 2);
  details.append(summary, content);
  entry.append(details);
}

async function buildGraph(dbName) {
  status.textContent = 'Building the schema graph...';
  try {
    const {response, data} = await requestJson('api.php?action=setup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: dbName})
    });
    status.textContent = data.status || data.error || 'Setup finished.';
    if (!response.ok) return false;
    localStorage.setItem(`graph2sql:${dbName}`, JSON.stringify(data));
    renderGraph(data);
    return true;
  } catch {
    status.textContent = 'The agent service is unavailable.';
    return false;
  }
}

async function loadDatabases() {
  try {
    const {response, data} = await requestJson('api.php?action=databases');
    database.replaceChildren(...(data.databases || []).map(name => new Option(name, name)));
    status.textContent = response.ok ? 'Agent service is ready.' : (data.error || 'Unable to load databases.');
    showCachedGraph();
  } catch {
    status.textContent = 'The agent service is unavailable.';
  }
}

document.querySelector('#setup').addEventListener('click', async () => {
  if (!database.value) return;
  buildGraph(database.value);
});

document.querySelector('#reset-database').addEventListener('click', async event => {
  const dbName = database.value;
  if (!dbName) return;
  const button = event.currentTarget;
  button.disabled = true;
  status.textContent = 'Restoring the original database...';
  try {
    const {response, data} = await requestJson('api.php?action=reset', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: dbName})
    });
    if (!response.ok) {
      status.textContent = data.error || 'The database could not be reset.';
      return;
    }
    localStorage.removeItem(`graph2sql:${dbName}`);
    if (await buildGraph(dbName)) status.textContent = 'Database reset; graph rebuilt.';
  } catch {
    status.textContent = 'The agent service is unavailable.';
  } finally {
    button.disabled = false;
  }
});

database.addEventListener('change', () => {
  if (!showCachedGraph()) {
    graph?._destructor?.();
    graph = null;
    document.querySelector('#graph').replaceChildren();
  }
});

function openTab(event, panelId) {
  document.querySelectorAll('.tabcontent').forEach(panel => { panel.hidden = true; });
  document.querySelectorAll('.tablinks').forEach(button => {
    button.classList.remove('active');
    button.setAttribute('aria-selected', 'false');
  });
  document.querySelector(`#${panelId}`).hidden = false;
  event.currentTarget.classList.add('active');
  event.currentTarget.setAttribute('aria-selected', 'true');
}

document.querySelectorAll('.tablinks').forEach(button => {
  button.addEventListener('click', event => openTab(event, button.dataset.panel));
});

async function submitPrompt(event, {input, output, action, edit = false}) {
  event.preventDefault();
  const prompt = input.value.trim();
  const selectedDatabase = database.value;
  if (!selectedDatabase || !prompt) return;

  output.querySelector('.chat-empty')?.remove();
  const entry = document.createElement('div');
  entry.className = 'chat-entry';
  output.append(entry);
  const addMessage = (className, text) => {
    const message = document.createElement('p');
    message.className = className;
    message.textContent = text;
    entry.append(message);
    output.scrollTop = output.scrollHeight;
    return message;
  };
  addMessage('chat-question', prompt);
  const pending = addMessage('chat-pending', edit ? 'Preparing change proposal...' : 'Thinking...');
  input.disabled = true;
  try {
    const {response, data} = await requestJson(`api.php?action=${action}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: selectedDatabase, prompt})
    });
    pending.remove();
    if (!response.ok) {
      addMessage('chat-error', data.error || 'The agent could not complete the request.');
      return;
    }

    addMessage('chat-answer', edit
      ? data.summary || 'Review the proposed change before applying it.'
      : data.answer || 'The agent returned no answer.');
    addDetails(entry, edit ? 'Proposed change' : 'SQL result', edit
      ? {kind: data.kind, sql: data.sql, join_condition: data.join_condition}
      : {sql: data.sql, rows: data.rows});
    if (data.telemetry) addDetails(entry, 'Telemetry', data.telemetry);
    if (edit) {
      const accept = document.createElement('button');
      accept.type = 'button';
      accept.textContent = 'Accept change';
      accept.addEventListener('click', async () => {
        accept.disabled = true;
        accept.textContent = 'Applying...';
        try {
          const {response: appliedResponse, data: applied} = await requestJson('api.php?action=edit_accept', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({db_name: selectedDatabase})
          });
          const appliedMessage = applied.graph_error
            ? `The database change was applied, but graph sync failed: ${applied.graph_error}`
            : applied.summary || 'Change applied.';
          addMessage(appliedResponse.ok ? 'chat-answer' : 'chat-error',
            appliedResponse.ok ? appliedMessage : applied.error || 'The change could not be applied.');
          if (appliedResponse.ok) {
            accept.remove();
            if (applied.graph_updated) localStorage.removeItem(`graph2sql:${selectedDatabase}`);
            addDetails(entry, 'Applied change details', {
              kind: applied.kind, sql: applied.sql, rows_affected: applied.rows_affected,
              graph_updated: applied.graph_updated, graph: applied.graph, graph_error: applied.graph_error
            });
            output.scrollTop = output.scrollHeight;

            const rebuilding = addMessage('chat-pending', 'Rebuilding the schema graph...');
            try {
              const {response: graphResponse, data: graphData} = await requestJson('api.php?action=setup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({db_name: selectedDatabase})
              });
              if (!graphResponse.ok) throw new Error(graphData.error || 'Graph rebuild failed.');
              rebuilding.remove();
              localStorage.setItem(`graph2sql:${selectedDatabase}`, JSON.stringify(graphData));
              renderGraph(graphData);
              addMessage('chat-answer', 'Schema graph rebuilt.');
            } catch (error) {
              rebuilding.remove();
              localStorage.removeItem(`graph2sql:${selectedDatabase}`);
              addMessage('chat-error', `Change applied, but the graph could not be rebuilt: ${error.message}`);
            }
          } else {
            accept.disabled = false;
            accept.textContent = 'Accept change';
          }
        } catch {
          addMessage('chat-error', 'The agent service is unavailable.');
          accept.disabled = false;
          accept.textContent = 'Accept change';
        }
      });
      entry.append(accept);
    }
    output.scrollTop = output.scrollHeight;
  } catch {
    pending.remove();
    addMessage('chat-error', 'The agent service is unavailable.');
  } finally {
    input.disabled = false;
    input.focus();
  }
}

document.querySelector('#agent-form').addEventListener('submit', event => {
  submitPrompt(event, {input: promptInput, output: qaChat, action: 'qa'});
});

document.querySelector('#edit-form').addEventListener('submit', event => {
  submitPrompt(event, {
    input: document.querySelector('#edit-prompt'),
    output: document.querySelector('#edit-chat'),
    action: 'edit',
    edit: true
  });
});

window.addEventListener('resize', () => {
  if (!graph) return;
  const container = document.querySelector('#graph');
  graph.width(container.clientWidth).height(container.clientHeight);
});

loadDatabases();
