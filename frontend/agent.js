const agentForm = document.querySelector('#agent-form');
const agentPrompt = document.querySelector('#agent-prompt');
const chat = document.querySelector('#chat');

async function readAgentJson(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (error) {
    return {error: `Agent returned a non-JSON response (${response.status}).`};
  }
}

function addChatMessage(className, text) {
  const message = document.createElement('p');
  message.className = className;
  message.textContent = text;
  chat.append(message);
  return message;
}

agentForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = agentPrompt.value.trim();
  const database = document.querySelector('#database').value;
  if (!database || !prompt) return;

  chat.replaceChildren();
  addChatMessage('chat-question', prompt);
  const pending = addChatMessage('chat-pending', 'Thinking...');
  agentPrompt.disabled = true;

  try {
    const response = await fetch('api.php?action=qa', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({db_name: database, prompt})
    });
    const data = await readAgentJson(response);
    pending.remove();

    if (!response.ok) {
      addChatMessage('chat-error', data.error || 'The agent could not answer.');
      return;
    }

    addChatMessage('chat-answer', data.answer || 'The agent returned no answer.');
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'SQL result';
    const result = document.createElement('pre');
    result.textContent = JSON.stringify({sql: data.sql, rows: data.rows}, null, 2);
    details.append(summary, result);
    chat.append(details);
  } catch (error) {
    pending.remove();
    addChatMessage('chat-error', 'The agent service is unavailable.');
  } finally {
    agentPrompt.disabled = false;
    agentPrompt.focus();
  }
});
