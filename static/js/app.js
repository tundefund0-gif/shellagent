let chatHistory = [];
let autoExecute = true;
let isStreaming = false;
let currentProvider = 'openai';
let currentModel = '';
let providerModels = {};

const chatArea = document.getElementById('chatArea');
const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const modelDropdown = document.getElementById('modelDropdown');
const statusDot = document.getElementById('statusDot');

// ─── Init ─────────────────────────────────────────────────────────────
async function init() {
  try {
    const resp = await fetch('/api/providers');
    providerModels = await resp.json();
    // Set first available model
    for (const [pid, info] of Object.entries(providerModels)) {
      if (info.models.length > 0) {
        currentProvider = pid;
        currentModel = info.models[0];
        break;
      }
    }
    updateProviderUI();
  } catch (e) {
    console.error('Failed to load providers:', e);
  }
  userInput.focus();
}

// ─── Provider ─────────────────────────────────────────────────────────
function setProvider(pid) {
  if (!providerModels[pid]) return;
  currentProvider = pid;
  const models = providerModels[pid].models;
  currentModel = models.length > 0 ? models[0] : '';
  updateProviderUI();
}

function updateProviderUI() {
  // Update tabs
  document.querySelectorAll('.provider-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.provider === currentProvider);
  });
  // Update model display
  document.getElementById('currentModel').textContent = currentModel || 'none';
  const pName = providerModels[currentProvider]?.name || currentProvider;
  document.getElementById('providerInfo').textContent = `${pName} · ${currentModel}`;
}

function toggleModelDropdown() {
  if (modelDropdown.classList.contains('show')) {
    modelDropdown.classList.remove('show');
    return;
  }
  // Position dropdown
  const rect = document.getElementById('modelSelector').getBoundingClientRect();
  modelDropdown.style.top = (rect.bottom + 4) + 'px';
  modelDropdown.style.left = Math.max(10, rect.left + rect.width / 2 - 140) + 'px';

  let html = '';
  for (const [pid, info] of Object.entries(providerModels)) {
    html += `<div class="dd-section">${info.name}</div>`;
    if (info.models.length === 0) {
      html += `<div class="dd-item" style="color:var(--text4);cursor:default">No models available</div>`;
    }
    for (const m of info.models) {
      const sel = pid === currentProvider && m === currentModel ? ' selected' : '';
      html += `<div class="dd-item${sel}" onclick="pickModel('${pid}','${escapeAttr(m)}')">
        <span class="dd-dot ${pid}"></span>${escapeHtml(m)}</div>`;
    }
  }
  modelDropdown.innerHTML = html;
  modelDropdown.classList.add('show');
}

function pickModel(pid, model) {
  currentProvider = pid;
  currentModel = model;
  modelDropdown.classList.remove('show');
  updateProviderUI();
}

function escapeAttr(s) {
  return s.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.model-selector') && !e.target.closest('.model-dropdown')) {
    modelDropdown.classList.remove('show');
  }
});

// ─── Auto-execute ─────────────────────────────────────────────────────
function setAutoExec(val) {
  autoExecute = val;
  document.getElementById('autoMode').classList.toggle('active', val);
  document.getElementById('manualMode').classList.toggle('active', !val);
  document.getElementById('autoExecBadge').textContent = `Auto-execute: ${val ? 'ON' : 'OFF'}`;
  document.getElementById('autoExecBadge').style.color = val ? 'var(--green)' : 'var(--text4)';
}

// ─── Input ────────────────────────────────────────────────────────────
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

userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
});

// ─── Escape / Markdown ────────────────────────────────────────────────
function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t;
  return d.innerHTML;
}

function renderMarkdown(text) {
  let h = escapeHtml(text);
  // Code blocks
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
    const label = lang ? `<span class="lang-label">${lang}</span>` : '';
    return `<pre>${label}${code}</pre>`;
  });
  // Inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic
  h = h.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Headers
  h = h.replace(/^### (.+)$/gm, '<strong style="font-size:15px">$1</strong>');
  h = h.replace(/^## (.+)$/gm, '<strong style="font-size:16px">$1</strong>');
  h = h.replace(/^# (.+)$/gm, '<strong style="font-size:18px">$1</strong>');
  // Lists
  h = h.replace(/^- (.+)$/gm, '• $1');
  // Paragraphs
  h = h.split('\n\n').map(p => {
    if (p.includes('<pre>')) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');
  return h;
}

// ─── Messages ─────────────────────────────────────────────────────────
function addMessage(role, content, streaming = false) {
  welcomeEl.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'message';
  const ac = role === 'user' ? 'user' : role === 'system' ? 'system' : 'agent';
  const nc = role === 'user' ? 'user-name' : role === 'system' ? 'system-name' : 'agent-name';
  const label = role === 'user' ? 'You' : role === 'system' ? 'System' : 'ShellAgent';
  const initial = role === 'user' ? 'Y' : role === 'system' ? '⚡' : 'S';
  div.innerHTML = `
    <div class="msg-avatar ${ac}">${initial}</div>
    <div class="msg-body">
      <div class="msg-name ${nc}">${label}</div>
      <div class="msg-content">${streaming ? '<span class="cursor"></span>' : renderMarkdown(content)}</div>
    </div>`;
  messagesEl.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  return div;
}

function addCommandOutput(cmd, output) {
  const wrapper = document.createElement('div');
  wrapper.className = 'cmd-output running';
  wrapper.innerHTML = `
    <div class="cmd-output-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
      <span>$ ${escapeHtml(cmd.trim())}</span>
    </div>
    <div class="cmd-output-body">${escapeHtml(output)}</div>`;
  const lastMsg = messagesEl.querySelector('.message:last-child .msg-body');
  if (lastMsg) lastMsg.appendChild(wrapper);
  chatArea.scrollTop = chatArea.scrollHeight;
  return wrapper;
}

function updateCommandOutput(wrapper, output) {
  wrapper.classList.remove('running');
  const body = wrapper.querySelector('.cmd-output-body');
  if (body) body.textContent = output;
}

function addSummary(text) {
  const div = document.createElement('div');
  div.className = 'summary-block';
  div.innerHTML = renderMarkdown(text);
  const lastMsg = messagesEl.querySelector('.message:last-child .msg-body');
  if (lastMsg) lastMsg.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ─── Send Message ─────────────────────────────────────────────────────
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  userInput.value = '';
  userInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;
  statusDot.className = 'status-dot';

  addMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const agentDiv = addMessage('assistant', '', true);
  const contentEl = agentDiv.querySelector('.msg-content');
  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: chatHistory,
        provider: currentProvider,
        model: currentModel,
        auto_execute: autoExecute
      })
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentWrapper = null;

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

          switch (parsed.type) {
            case 'token':
              fullText += parsed.data;
              contentEl.innerHTML = renderMarkdown(fullText) + '<span class="cursor"></span>';
              chatArea.scrollTop = chatArea.scrollHeight;
              break;

            case 'done':
              contentEl.innerHTML = renderMarkdown(fullText);
              break;

            case 'executing':
              currentWrapper = addCommandOutput(parsed.data, '⏳ Running...');
              break;

            case 'output':
              if (currentWrapper) {
                updateCommandOutput(currentWrapper, parsed.data);
                currentWrapper = null;
              }
              break;

            case 'summary_token':
              if (!document.querySelector('.summary-block')) {
                addSummary('');
              }
              const sb = document.querySelector('.summary-block:last-child');
              if (sb) {
                sb.innerHTML = renderMarkdown(
                  (sb.textContent || '') + parsed.data
                );
              }
              break;

            case 'summary_done':
              const sbFinal = document.querySelector('.summary-block:last-child');
              if (sbFinal) sbFinal.innerHTML = renderMarkdown(parsed.data);
              break;

            case 'error':
              statusDot.className = 'status-dot error';
              fullText += `\n\n⚠️ ${parsed.data}`;
              contentEl.innerHTML = renderMarkdown(fullText);
              break;
          }
        } catch (e) {}
      }
    }

    // Ensure cursor is removed
    contentEl.innerHTML = renderMarkdown(fullText);
    chatHistory.push({ role: 'assistant', content: fullText });

  } catch (e) {
    statusDot.className = 'status-dot error';
    contentEl.innerHTML = renderMarkdown(`⚠️ Connection error: ${e.message}`);
  }

  isStreaming = false;
  sendBtn.disabled = false;
  chatArea.scrollTop = chatArea.scrollHeight;
  userInput.focus();
}

// ─── Boot ─────────────────────────────────────────────────────────────
init();
