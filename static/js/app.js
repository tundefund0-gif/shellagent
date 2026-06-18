let chatHistory = [];
let isStreaming = false;
let currentProvider = 'openai';
let currentModel = '';
let providerModels = {};
let currentPlan = [];
let commandHistory = [];
let sessions = [];
let totalTokens = 0;

const chatArea = document.getElementById('chatArea');
const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const modelDropdown = document.getElementById('modelDropdown');
const statusDot = document.getElementById('statusDot');
const iterBadge = document.getElementById('iterBadge');
const iterText = document.getElementById('iterText');
const tokenBadge = document.getElementById('tokenBadge');
const tokenText = document.getElementById('tokenText');

const TOOL_META = {
  execute_shell_command: { icon: '⚡', label: 'Shell', color: 'var(--green)' },
  web_search:            { icon: '🔍', label: 'Search', color: 'var(--accent)' },
  web_fetch:             { icon: '🌐', label: 'Fetch', color: 'var(--purple)' },
  read_file:             { icon: '📖', label: 'Read', color: 'var(--yellow)' },
  write_file:            { icon: '✏️', label: 'Write', color: 'var(--orange)' },
  list_directory:        { icon: '📁', label: 'List', color: 'var(--text2)' },
  update_plan:           { icon: '📋', label: 'Plan', color: 'var(--purple)' },
  git_commit:            { icon: '🔀', label: 'Commit', color: 'var(--green)' },
  validate_changes:      { icon: '✅', label: 'Validate', color: 'var(--green)' },
  list_git_changes:      { icon: '📊', label: 'Git', color: 'var(--accent)' },
};
function getToolMeta(n) { return TOOL_META[n] || { icon: '🔧', label: n, color: 'var(--text2)' }; }

// ─── Init ─────────────────────────────────────────────────────────────
async function init() {
  try {
    const [provResp, cwdResp, sessResp] = await Promise.all([
      fetch('/api/providers'),
      fetch('/api/cwd'),
      fetch('/api/sessions').catch(() => null),
    ]);
    providerModels = await provResp.json();
    const cwdData = await cwdResp.json();
    if (cwdData.cwd) document.getElementById('cwdDisplay').textContent = cwdData.cwd;
    if (sessResp) { const sd = await sessResp.json(); sessions = sd.sessions || []; renderSessions(); }
    for (const [pid, info] of Object.entries(providerModels)) {
      if (info.models.length > 0) { currentProvider = pid; currentModel = info.models[0]; break; }
    }
    updateProviderUI();
  } catch (e) { console.error(e); }
  userInput.focus();
  loadHistory();
}

// ─── Provider ─────────────────────────────────────────────────────────
function setProvider(pid) {
  if (!providerModels[pid]) return;
  currentProvider = pid;
  currentModel = providerModels[pid].models[0] || '';
  updateProviderUI();
}
function updateProviderUI() {
  document.querySelectorAll('.provider-btn').forEach(b => b.classList.toggle('active', b.dataset.provider === currentProvider));
  document.getElementById('currentModel').textContent = currentModel || 'none';
  const pName = providerModels[currentProvider]?.name || currentProvider;
  document.getElementById('providerInfo').textContent = `${pName} · ${currentModel} · 10 tools`;
}
function toggleModelDropdown() {
  if (modelDropdown.classList.contains('show')) { modelDropdown.classList.remove('show'); return; }
  const rect = document.getElementById('modelSelector').getBoundingClientRect();
  modelDropdown.style.top = (rect.bottom + 4) + 'px';
  modelDropdown.style.left = Math.max(10, rect.left + rect.width / 2 - 130) + 'px';
  let html = '';
  for (const [pid, info] of Object.entries(providerModels)) {
    html += `<div class="dd-section">${info.name}</div>`;
    if (!info.models.length) html += `<div class="dd-item" style="color:var(--text4);cursor:default">No models</div>`;
    for (const m of info.models) {
      const sel = pid === currentProvider && m === currentModel ? ' selected' : '';
      html += `<div class="dd-item${sel}" onclick="pickModel('${pid}','${esc(m)}')"><span class="dd-dot ${pid}"></span>${h(m)}</div>`;
    }
  }
  modelDropdown.innerHTML = html;
  modelDropdown.classList.add('show');
}
function pickModel(pid, model) { currentProvider = pid; currentModel = model; modelDropdown.classList.remove('show'); updateProviderUI(); }
document.addEventListener('click', e => { if (!e.target.closest('.model-selector') && !e.target.closest('.model-dropdown')) modelDropdown.classList.remove('show'); });

// ─── CWD ──────────────────────────────────────────────────────────────
function toggleCwdEdit() {
  const btn = document.getElementById('cwdBtn');
  const wrap = document.getElementById('cwdInputWrap');
  const input = document.getElementById('cwdInput');
  if (wrap.style.display === 'none') {
    btn.style.display = 'none';
    wrap.style.display = 'flex';
    input.value = document.getElementById('cwdDisplay').textContent;
    input.focus();
    input.select();
  } else {
    btn.style.display = 'flex';
    wrap.style.display = 'none';
  }
}
async function changeCwd() {
  const input = document.getElementById('cwdInput');
  const path = input.value.trim();
  if (!path) return toggleCwdEdit();
  try {
    const resp = await fetch('/api/cwd', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({cwd: path}) });
    const data = await resp.json();
    if (data.cwd) {
      document.getElementById('cwdDisplay').textContent = data.cwd;
      addSystemMsg(`Working directory changed to ${data.cwd}`);
    } else if (data.error) {
      addSystemMsg(`Error: ${data.error}`);
    }
  } catch (e) { addSystemMsg(`Error: ${e.message}`); }
  toggleCwdEdit();
}

// ─── Input ────────────────────────────────────────────────────────────
function sendQuick(t) { userInput.value = t; sendMessage(); }
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}
userInput.addEventListener('input', () => { userInput.style.height = 'auto'; userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px'; });

// ─── HTML ─────────────────────────────────────────────────────────────
function h(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function esc(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }
function renderMd(text) {
  let html = h(text);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) => `<pre>${lang ? `<span class="lang-label">${lang}</span>` : ''}${code}</pre>`);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.split('\n\n').map(p => p.includes('<pre>') ? p : `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
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
  div.innerHTML = `<div class="msg-avatar ${ac}">${init}</div><div class="msg-body"><div class="msg-name ${nc}">${label}</div><div class="msg-content">${stream ? '<span class="cursor"></span>' : renderMd(content)}</div></div>`;
  messagesEl.appendChild(div);
  scroll();
  return div;
}
function addSystemMsg(text) {
  const div = document.createElement('div');
  div.className = 'message';
  div.innerHTML = `<div class="msg-avatar" style="background:var(--bg4);color:var(--text3)">⚡</div><div class="msg-body"><div class="msg-name" style="color:var(--text4)">System</div><div class="msg-content" style="color:var(--text3);font-size:12px">${h(text)}</div></div>`;
  messagesEl.appendChild(div);
  scroll();
}

// ─── Plan sidebar ─────────────────────────────────────────────────────
function renderPlan() {
  const list = document.getElementById('planList');
  const count = document.getElementById('planCount');
  count.textContent = currentPlan.length;
  if (!currentPlan.length) { list.innerHTML = '<div class="plan-empty">No plan yet</div>'; return; }
  list.innerHTML = currentPlan.map(p => `
    <div class="plan-item ${p.status}">
      <div class="plan-dot ${p.status}"></div>
      <div class="plan-text">${h(p.step)}</div>
    </div>`).join('');
}

// ─── Command history sidebar ──────────────────────────────────────────
function addHistoryEntry(name, cmd, success) {
  const list = document.getElementById('historyList');
  const empty = list.querySelector('.plan-empty');
  if (empty) empty.remove();
  const meta = getToolMeta(name);
  const entry = document.createElement('div');
  entry.className = 'history-item';
  entry.innerHTML = `<span class="history-icon">${meta.icon}</span><span class="history-text">${h(cmd)}</span><span class="history-badge ${success ? 'ok' : 'fail'}">${success ? 'ok' : 'err'}</span>`;
  list.insertBefore(entry, list.firstChild);
  if (list.children.length > 50) list.removeChild(list.lastChild);
  commandHistory.push({ name, cmd, success, time: Date.now() });
  saveHistory();
}
function saveHistory() {
  try { localStorage.setItem('sa_history', JSON.stringify(commandHistory.slice(-100))); } catch(e) {}
}
function loadHistory() {
  try {
    const data = JSON.parse(localStorage.getItem('sa_history') || '[]');
    commandHistory = data;
    const list = document.getElementById('historyList');
    if (data.length) {
      list.innerHTML = '';
      data.slice(-20).reverse().forEach(e => {
        const meta = getToolMeta(e.name);
        const entry = document.createElement('div');
        entry.className = 'history-item';
        entry.innerHTML = `<span class="history-icon">${meta.icon}</span><span class="history-text">${h(e.cmd)}</span><span class="history-badge ${e.success ? 'ok' : 'fail'}">${e.success ? 'ok' : 'err'}</span>`;
        list.appendChild(entry);
      });
    }
  } catch(e) {}
}

// ─── Sessions sidebar ────────────────────────────────────────────────
function renderSessions() {
  const list = document.getElementById('sessionsList');
  if (!sessions.length) { list.innerHTML = '<div class="plan-empty">No sessions</div>'; return; }
  list.innerHTML = sessions.slice(0, 10).map(s => {
    const date = new Date(s.saved_at * 1000).toLocaleTimeString();
    return `<div class="session-item" onclick="loadSession('${s.id}')"><span style="font-size:10px">${date}</span> <span>${s.messages} msgs</span></div>`;
  }).join('');
}
async function loadSession(id) {
  try {
    const resp = await fetch(`/api/session/${id}`);
    const data = await resp.json();
    if (data.messages) {
      chatHistory = data.messages.filter(m => m.role !== 'system' && m.role !== 'tool');
      messagesEl.innerHTML = '';
      welcomeEl.style.display = 'none';
      chatHistory.forEach(m => { if (m.role === 'user' || m.role === 'assistant') addMsg(m.role, m.content || ''); });
      addSystemMsg(`Loaded session ${id}`);
    }
  } catch (e) { addSystemMsg(`Failed to load session: ${e.message}`); }
}

// ─── Tool call UI ─────────────────────────────────────────────────────
function addToolCall(id, name, args) {
  const meta = getToolMeta(name);
  let argStr = '';
  if (args.command) argStr = args.command;
  else if (args.query) argStr = args.query;
  else if (args.url) argStr = args.url;
  else if (args.path) argStr = args.path;
  else if (args.message) argStr = args.message;
  else if (args.mode) argStr = args.mode;
  else argStr = JSON.stringify(args).substring(0, 80);
  const div = document.createElement('div');
  div.className = 'tool-call';
  div.id = `tc-${id}`;
  div.innerHTML = `<div class="tool-header running"><span class="tool-icon">${meta.icon}</span><span class="tool-label" style="color:${meta.color}">${meta.label}</span><span class="tool-cmd">${h(argStr)}</span><span class="tool-badge running">running</span></div><div class="tool-output">⏳ Executing...</div>`;
  const lastMsg = messagesEl.querySelector('.message:last-child .msg-body');
  if (lastMsg) lastMsg.appendChild(div);
  scroll();
  return div;
}
function updateToolResult(id, output, success, exitCode, name) {
  const el = document.getElementById(`tc-${id}`);
  if (!el) return;
  const header = el.querySelector('.tool-header');
  const badge = el.querySelector('.tool-badge');
  const outEl = el.querySelector('.tool-output');
  header.classList.remove('running');
  header.classList.add(success ? 'success' : 'failed');
  badge.className = `tool-badge ${success ? 'success' : 'failed'}`;
  badge.textContent = success ? 'done' : 'failed';
  if (exitCode !== undefined && exitCode !== null) {
    const ec = document.createElement('span');
    ec.className = `exit-code ${success ? 'exit-ok' : 'exit-fail'}`;
    ec.textContent = `exit ${exitCode}`;
    badge.parentNode.appendChild(ec);
  }
  outEl.textContent = output.length > 4000 ? output.substring(0, 4000) + '\n\n[truncated]' : output;
  // Add to command history
  const cmd = el.querySelector('.tool-cmd')?.textContent || '';
  addHistoryEntry(name || 'shell', cmd, success);
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

// ─── Send ─────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;
  userInput.value = '';
  userInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;
  totalTokens = 0;
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
            case 'iteration': addIterSep(p.data); iterBadge.style.display = 'flex'; iterText.textContent = p.data; break;
            case 'token': fullText += p.data; contentEl.innerHTML = renderMd(fullText) + '<span class="cursor"></span>'; scroll(); break;
            case 'done': contentEl.innerHTML = renderMd(p.data || fullText); chatHistory.push({ role: 'assistant', content: p.data || fullText }); break;
            case 'tool_call': { const tc = typeof p.data === 'string' ? JSON.parse(p.data) : p.data; addToolCall(tc.id || `tc-${Date.now()}`, tc.name || '', tc.args || {}); break; }
            case 'tool_result': { const tr = typeof p.data === 'string' ? JSON.parse(p.data) : p.data; updateToolResult(tr.id, tr.output || '', tr.success, tr.exit_code, tr.name); break; }
            case 'plan': { currentPlan = p.data || []; renderPlan(); break; }
            case 'tokens': { const t = p.data || {}; totalTokens = (t.prompt || 0) + (t.completion || 0); tokenBadge.style.display = 'flex'; tokenText.textContent = `${totalTokens.toLocaleString()} tok`; break; }
            case 'tokens_final': { const t = p.data || {}; totalTokens = (t.prompt || 0) + (t.completion || 0); tokenText.textContent = `${totalTokens.toLocaleString()} tok`; break; }
            case 'session_saved': addSystemMsg(`Session saved: ${p.data}`); break;
            case 'error': statusDot.className = 'status-dot error'; fullText += `\n\n⚠️ ${p.data}`; contentEl.innerHTML = renderMd(fullText); break;
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
  // Refresh sessions
  try { const resp = await fetch('/api/sessions'); const sd = await resp.json(); sessions = sd.sessions || []; renderSessions(); } catch(e) {}
}

init();
