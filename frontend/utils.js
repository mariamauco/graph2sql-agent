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
  status.textContent = 'Building the schema graph...';
  try {
    const {response, data} = await requestJson('api.php?action=setup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: database.value})
    });
    status.textContent = data.status || data.error || 'Setup finished.';
    if (!response.ok) return;
    localStorage.setItem(`graph2sql:${database.value}`, JSON.stringify(data));
    renderGraph(data);
  } catch {
    status.textContent = 'The agent service is unavailable.';
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
  if (!database.value || !prompt) return;

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
  const pending = addMessage('chat-pending', edit ? 'Applying change...' : 'Thinking...');
  input.disabled = true;
  try {
    const {response, data} = await requestJson(`api.php?action=${action}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: database.value, prompt})
    });
    pending.remove();
    if (!response.ok) {
      addMessage('chat-error', data.error || 'The agent could not complete the request.');
      return;
    }

    addMessage('chat-answer', edit
      ? data.summary || 'The change was applied.'
      : data.answer || 'The agent returned no answer.');
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = edit ? 'Change details' : 'SQL result';
    const result = document.createElement('pre');
    result.textContent = JSON.stringify(edit
      ? {sql: data.sql || data.sql_executed, rows_affected: data.rows_affected,
        graph_updated: data.graph_updated ?? data.graph_synced}
      : {sql: data.sql, rows: data.rows}, null, 2);
    details.append(summary, result);
    entry.append(details);
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
