let chatHistory = [];
let autoExecute = true;
let isStreaming = false;

const chatArea = document.getElementById('chatArea');
const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

function toggleModelDropdown() {
  document.getElementById('modelDropdown').classList.toggle('show');
}

function setModel(m) {
  document.getElementById('currentModel').textContent = m;
  document.getElementById('modelDropdown').classList.remove('show');
}

function setAutoExec(val) {
  autoExecute = val;
  document.getElementById('autoMode').classList.toggle('active', val);
  document.getElementById('manualMode').classList.toggle('active', !val);
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.model-selector') && !e.target.closest('.model-dropdown')) {
    document.getElementById('modelDropdown').classList.remove('show');
  }
});

function sendQuick(text) {
  userInput.value = text;
  sendMessage();
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// Auto-resize textarea
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
});

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function renderMarkdown(text) {
  let html = escapeHtml(text);
  // Code blocks with language labels
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
    const label = lang ? `<span class="lang-label">${lang}</span>` : '';
    return `<pre>${label}${code}</pre>`;
  });
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Line breaks to paragraphs
  html = html.split('\n\n').map(p => {
    if (p.startsWith('<pre>') || p.includes('<pre>')) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');
  return html;
}

function addMessage(role, content, streaming = false) {
  welcomeEl.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'message';
  const avatarClass = role === 'user' ? 'user' : 'agent';
  const nameClass = role === 'user' ? 'user-name' : 'agent-name';
  const label = role === 'user' ? 'You' : 'ShellAgent';
  div.innerHTML = `
    <div class="msg-avatar ${avatarClass}">${role === 'user' ? 'Y' : 'S'}</div>
    <div class="msg-body">
      <div class="msg-name ${nameClass}">${label}</div>
      <div class="msg-content">${streaming ? '<span class="cursor"></span>' : renderMarkdown(content)}</div>
    </div>`;
  messagesEl.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function addCommandOutput(cmd, output) {
  const div = document.createElement('div');
  div.className = 'cmd-output';
  div.innerHTML = `
    <div class="cmd-output-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
      <span>$ ${escapeHtml(cmd.trim())}</span>
    </div>
    <div class="cmd-output-body">${escapeHtml(output)}</div>`;
  const lastMsg = messagesEl.querySelector('.message:last-child .msg-body');
  if (lastMsg) lastMsg.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  userInput.value = '';
  userInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;

  addMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const agentDiv = addMessage('assistant', '', true);
  const contentEl = agentDiv.querySelector('.msg-content');
  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: chatHistory, auto_execute: false })
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const event of events) {
        const lines = event.split('\n');
        let eventType = '';
        let data = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          if (line.startsWith('data: ')) data = line.slice(6);
        }
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.type === 'token') {
            fullText += parsed.data;
            contentEl.innerHTML = renderMarkdown(fullText) + '<span class="cursor"></span>';
            chatArea.scrollTop = chatArea.scrollHeight;
          } else if (parsed.type === 'executing') {
            addCommandOutput(parsed.data, '⏳ Running...');
          } else if (parsed.type === 'output') {
            const bodies = messagesEl.querySelectorAll('.cmd-output-body');
            if (bodies.length) {
              const last = bodies[bodies.length - 1];
              last.textContent = parsed.data;
            }
          } else if (parsed.type === 'error') {
            fullText += `\n\n⚠️ Error: ${parsed.data}`;
            contentEl.innerHTML = renderMarkdown(fullText);
          }
        } catch (e) {}
      }
    }

    contentEl.innerHTML = renderMarkdown(fullText);
    chatHistory.push({ role: 'assistant', content: fullText });

  } catch (e) {
    contentEl.innerHTML = renderMarkdown(`⚠️ Connection error: ${e.message}`);
  }

  isStreaming = false;
  sendBtn.disabled = false;
  chatArea.scrollTop = chatArea.scrollHeight;
  userInput.focus();
}

// Init
userInput.focus();
