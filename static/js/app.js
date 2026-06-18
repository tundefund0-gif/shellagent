let chatHistory = [];
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
const iterBadge = document.getElementById('iterBadge');
const iterText = document.getElementById('iterText');

async function init() {
  try {
    const resp = await fetch('/api/providers');
    providerModels = await resp.json();
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
  document.querySelectorAll('.provider-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.provider === currentProvider);
  });
  document.getElementById('currentModel').textContent = currentModel || 'none';
  const pName = providerModels[currentProvider]?.name || currentProvider;
  const tools = providerModels[currentProvider]?.supports_tools;
  document.getElementById('providerInfo').textContent = `${pName} · ${currentModel} · ${tools ? 'tool calling' : 'code blocks'}`;
}

function toggleModelDropdown() {
  if (modelDropdown.classList.contains('show')) {
    modelDropdown.classList.remove('show');
    return;
  }
  const rect = document.getElementById('modelSelector').getBoundingClientRect();
  modelDropdown.style.top = (rect.bottom + 4) + 'px';
  modelDropdown.style.left = Math.max(10, rect.left + rect.width / 2 - 140) + 'px';

  let html = '';
  for (const [pid, info] of Object.entries(providerModels)) {
    html += `<div class="dd-section">${info.name}${info.supports_tools ? ' ⚡' : ''}</div>`;
    if (info.models.length === 0) {
      html += `<div class="dd-item" style="color:var(--text4);cursor:default">No models found</div>`;
    }
    for (const m of info.models) {
      const sel = pid === currentProvider && m === currentModel ? ' selected' : '';
      html += `<div class="dd-item${sel}" onclick="pickModel('${pid}','${esc(m)}')"><span class="dd-dot ${pid}"></span>${h(m)}</div>`;
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

document.addEventListener('click', e => {
  if (!e.target.closest('.model-selector') && !e.target.closest('.model-dropdown'))
    modelDropdown.classList.remove('show');
});

// ─── Input ────────────────────────────────────────────────────────────
function sendQuick(text) { userInput.value = text; sendMessage(); }
function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
});

// ─── HTML helpers ─────────────────────────────────────────────────────
function h(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function esc(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

function renderMd(text) {
  let html = h(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => {
    const label = lang ? `<span class="lang-label">${lang}</span>` : '';
    return `<pre>${label}${code}</pre>`;
  });
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/^### (.+)$/gm, '<strong style="font-size:14px">$1</strong>');
  html = html.replace(/^## (.+)$/gm, '<strong style="font-size:15px">$1</strong>');
  html = html.replace(/^# (.+)$/gm, '<strong style="font-size:17px">$1</strong>');
  html = html.replace(/^- (.+)$/gm, '• $1');
  html = html.split('\n\n').map(p => {
    if (p.includes('<pre>')) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');
  return html;
}

// ─── Messages ─────────────────────────────────────────────────────────
function addMsg(role, content, stream = false) {
  welcomeEl.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'message';
  const ac = role === 'user' ? 'user' : 'agent';
  const nc = role === 'user' ? 'user-name' : 'agent-name';
  const label = role === 'user' ? 'You' : 'ShellAgent';
  const init = role === 'user' ? 'Y' : 'S';
  div.innerHTML = `<div class="msg-avatar ${ac}">${init}</div>
    <div class="msg-body">
      <div class="msg-name ${nc}">${label}</div>
      <div class="msg-content">${stream ? '<span class="cursor"></span>' : renderMd(content)}</div>
    </div>`;
  messagesEl.appendChild(div);
  scroll();
  return div;
}

function addToolCall(id, command) {
  const div = document.createElement('div');
  div.className = 'tool-call';
  div.id = `tc-${id}`;
  div.innerHTML = `
    <div class="tool-header running">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
      <span class="tool-cmd">$ ${h(command)}</span>
      <span class="tool-badge running">running</span>
    </div>
    <div class="tool-output">⏳ Executing...</div>`;
  const lastMsg = messagesEl.querySelector('.message:last-child .msg-body');
  if (lastMsg) lastMsg.appendChild(div);
  scroll();
  return div;
}

function updateToolResult(id, output, success, exitCode) {
  const el = document.getElementById(`tc-${id}`);
  if (!el) return;
  const header = el.querySelector('.tool-header');
  const badge = el.querySelector('.tool-badge');
  const outEl = el.querySelector('.tool-output');
  header.classList.remove('running');
  header.classList.add(success ? 'success' : 'failed');
  badge.className = `tool-badge ${success ? 'success' : 'failed'}`;
  badge.textContent = success ? 'done' : 'failed';
  if (exitCode !== undefined) {
    const ec = document.createElement('span');
    ec.className = `exit-code ${success ? 'exit-ok' : 'exit-fail'}`;
    ec.textContent = `exit ${exitCode}`;
    badge.parentNode.appendChild(ec);
  }
  outEl.textContent = output;
  scroll();
}

function addIterSep(num) {
  const div = document.createElement('div');
  div.className = 'iter-sep';
  div.textContent = `iteration ${num}`;
  messagesEl.appendChild(div);
  scroll();
}

function scroll() { chatArea.scrollTop = chatArea.scrollHeight; }

// ─── Main send ────────────────────────────────────────────────────────
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;
  userInput.value = '';
  userInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;
  statusDot.className = 'status-dot running';

  addMsg('user', text);
  chatHistory.push({ role: 'user', content: text });

  const agentDiv = addMsg('assistant', '', true);
  const contentEl = agentDiv.querySelector('.msg-content');
  let fullText = '';

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: chatHistory, provider: currentProvider, model: currentModel })
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let currentToolId = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const events = buf.split('\n\n');
      buf = events.pop() || '';

      for (const ev of events) {
        let eventType = '', data = '';
        for (const line of ev.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7);
          if (line.startsWith('data: ')) data = line.slice(6);
        }
        if (!data) continue;

        try {
          const p = JSON.parse(data);
          switch (p.type) {
            case 'iteration':
              addIterSep(p.data);
              iterBadge.style.display = 'flex';
              iterText.textContent = p.data;
              break;
            case 'token':
              fullText += p.data;
              contentEl.innerHTML = renderMd(fullText) + '<span class="cursor"></span>';
              scroll();
              break;
            case 'done':
              contentEl.innerHTML = renderMd(p.data || fullText);
              chatHistory.push({ role: 'assistant', content: p.data || fullText });
              break;
            case 'tool_call':
              const tc = typeof p.data === 'string' ? JSON.parse(p.data) : p.data;
              currentToolId = tc.id || `tc-${Date.now()}`;
              addToolCall(currentToolId, tc.command || '');
              break;
            case 'tool_result': {
              const tr = typeof p.data === 'string' ? JSON.parse(p.data) : p.data;
              updateToolResult(tr.id || currentToolId, tr.output || '', tr.success, tr.exit_code);
              break;
            }
            case 'error':
              statusDot.className = 'status-dot error';
              fullText += `\n\n⚠️ ${p.data}`;
              contentEl.innerHTML = renderMd(fullText);
              break;
          }
        } catch (e) {}
      }
    }

    if (!fullText) contentEl.innerHTML = renderMd('');

  } catch (e) {
    statusDot.className = 'status-dot error';
    contentEl.innerHTML = renderMd(`⚠️ Connection error: ${e.message}`);
  }

  isStreaming = false;
  sendBtn.disabled = false;
  statusDot.className = 'status-dot';
  iterBadge.style.display = 'none';
  scroll();
  userInput.focus();
}

init();
