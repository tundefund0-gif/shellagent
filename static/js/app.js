/* ─── ShellAgent v7.0 Frontend ─────────────────────────────────────── */

let chatHistory = [];
let isStreaming = false;
let currentProvider = 'openai';
let currentModel = '';
let providerModels = {};
let currentPlan = [];
let commandHistory = [];
let sessions = [];
let totalTokens = 0;
let sessionId = crypto.randomUUID ? crypto.randomUUID().slice(0, 16) : Math.random().toString(36).slice(2, 16);
let userScrolledUp = false;

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
  grep_search:           { icon: '🔎', label: 'Grep', color: 'var(--yellow)' },
  analyze_code:          { icon: '🔬', label: 'Analyze', color: 'var(--purple)' },
};
function getToolMeta(n) { return TOOL_META[n] || { icon: '🔧', label: n, color: 'var(--text2)' }; }

function init() {
  Promise.all([
    fetch('/api/providers'),
    fetch('/api/cwd'),
    fetch('/api/sessions').catch(function() { return null; }),
  ]).then(function(resps) {
    return Promise.all([resps[0].json(), resps[1].json(), resps[2] ? resps[2].json() : Promise.resolve(null)]);
  }).then(function(arr) {
    providerModels = arr[0];
    var cwdData = arr[1];
    if (cwdData.cwd) document.getElementById('cwdDisplay').textContent = cwdData.cwd;
    if (arr[2]) { sessions = arr[2].sessions || []; renderSessions(); }
    for (var pid in providerModels) {
      if (providerModels[pid].models.length > 0) { currentProvider = pid; currentModel = providerModels[pid].models[0]; break; }
    }
    updateProviderUI();
  }).catch(function(e) { console.error('Init failed:', e); });
  userInput.focus();
  loadHistory();
}

function setProvider(pid) {
  if (!providerModels[pid]) return;
  currentProvider = pid;
  currentModel = providerModels[pid].models[0] || '';
  updateProviderUI();
}

function updateProviderUI() {
  document.querySelectorAll('.provider-btn').forEach(function(b) { b.classList.toggle('active', b.dataset.provider === currentProvider); });
  document.getElementById('currentModel').textContent = currentModel || 'none';
  var pName = providerModels[currentProvider] ? providerModels[currentProvider].name : currentProvider;
  document.getElementById('providerInfo').textContent = pName + ' \u00b7 ' + currentModel + ' \u00b7 12 tools';
}

function toggleModelDropdown() {
  if (modelDropdown.classList.contains('show')) { modelDropdown.classList.remove('show'); return; }
  var rect = document.getElementById('modelSelector').getBoundingClientRect();
  modelDropdown.style.top = (rect.bottom + 4) + 'px';
  modelDropdown.style.left = Math.max(10, rect.left + rect.width / 2 - 130) + 'px';
  var html = '';
  for (var pid in providerModels) {
    var info = providerModels[pid];
    html += '<div class="dd-section">' + info.name + '</div>';
    if (!info.models.length) html += '<div class="dd-item" style="color:var(--text4);cursor:default">No models</div>';
    for (var i = 0; i < info.models.length; i++) {
      var m = info.models[i];
      var sel = pid === currentProvider && m === currentModel ? ' selected' : '';
      html += '<div class="dd-item' + sel + '" onclick="pickModel(\'' + pid + '\',\'' + esc(m) + '\')"><span class="dd-dot ' + pid + '"></span>' + h(m) + '</div>';
    }
  }
  modelDropdown.innerHTML = html;
  modelDropdown.classList.add('show');
}

function pickModel(pid, model) { currentProvider = pid; currentModel = model; modelDropdown.classList.remove('show'); updateProviderUI(); }
document.addEventListener('click', function(e) { if (!e.target.closest('.model-selector') && !e.target.closest('.model-dropdown')) modelDropdown.classList.remove('show'); });

function toggleCwdEdit() {
  var btn = document.getElementById('cwdBtn');
  var wrap = document.getElementById('cwdInputWrap');
  if (wrap.style.display === 'none') {
    btn.style.display = 'none';
    wrap.style.display = 'flex';
    document.getElementById('cwdInput').value = document.getElementById('cwdDisplay').textContent;
    document.getElementById('cwdInput').focus();
  } else {
    wrap.style.display = 'none';
    btn.style.display = 'flex';
  }
}

function changeCwd() {
  var val = document.getElementById('cwdInput').value.trim();
  if (!val) return;
  fetch('/api/cwd', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cwd: val }),
  }).then(function(resp) { return resp.json(); }).then(function(data) {
    if (data.cwd) {
      document.getElementById('cwdDisplay').textContent = data.cwd;
      addSystemMsg('Changed directory to ' + data.cwd);
    } else {
      addSystemMsg('Error: ' + (data.error || 'Failed'));
    }
  }).catch(function(e) { addSystemMsg('Error: ' + e.message); });
  document.getElementById('cwdInputWrap').style.display = 'none';
  document.getElementById('cwdBtn').style.display = 'flex';
}

function esc(s) { return s.replace(/'/g, "\\'").replace(/\\/g, "\\\\"); }
function h(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function renderMd(text) {
  if (!text) return '';
  var s = h(text);
  s = s.replace(/```(\w*)\n([\s\S]*?)```/g, function(m, lang, code) {
    return '<pre><code class="lang-' + (lang || 'text') + '">' + code + '</code><button class="copy-btn" onclick="copyCode(this)" aria-label="Copy code">Copy</button>' + (lang ? '<span class="lang-label">' + lang + '</span>' : '') + '</pre>';
  });
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  s = s.replace(/^- (.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  s = s.replace(/(https?:\/\/[^\s<"']+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/\n/g, '<br>');
  return s;
}

function copyCode(btn) {
  var code = btn.parentElement.querySelector('code');
  navigator.clipboard.writeText(code.textContent).then(function() {
    btn.textContent = 'Copied!';
    setTimeout(function() { btn.textContent = 'Copy'; }, 1500);
  });
}

function copyText(text) { navigator.clipboard.writeText(text).catch(function() {}); }

function addMsg(role, content, streaming) {
  if (welcomeEl) welcomeEl.style.display = 'none';
  var div = document.createElement('div');
  div.className = 'msg msg-' + role;
  var name = role === 'user' ? 'You' : 'ShellAgent';
  var icon = role === 'user' ? '\ud83d\udc64' : '\u26a1';
  div.innerHTML = '<div class="msg-head"><span class="msg-icon">' + icon + '</span><span class="msg-name">' + name + (streaming ? ' <span class="typing-dot">...</span>' : '') + '<button class="copy-msg-btn" onclick="copyText(this.closest(\'.msg\').querySelector(\'.msg-content\').textContent)" title="Copy message" aria-label="Copy message">\ud83d\udccb</button></span></div><div class="msg-content">' + (content ? renderMd(content) : '') + '</div>';
  messagesEl.appendChild(div);
  scroll();
  return div;
}

function addSystemMsg(content) {
  var div = document.createElement('div');
  div.className = 'msg msg-system';
  div.innerHTML = '<div class="msg-content" style="color:var(--text3);font-size:11px;text-align:center;font-style:italic">' + h(content) + '</div>';
  messagesEl.appendChild(div);
  scroll();
}

function addIterSep(n) {
  var div = document.createElement('div');
  div.className = 'iter-sep';
  div.textContent = 'Iteration ' + n;
  messagesEl.appendChild(div);
}

function addToolCall(id, name, args) {
  var meta = getToolMeta(name);
  var div = document.createElement('div');
  div.className = 'tool-call';
  div.id = 'tc-' + id;
  var argsStr = '';
  if (name === 'execute_shell_command') argsStr = args.command || '';
  else if (name === 'web_search') argsStr = args.query || '';
  else if (name === 'web_fetch') argsStr = args.url || '';
  else if (name === 'read_file' || name === 'analyze_code') argsStr = args.path || '';
  else if (name === 'write_file') argsStr = args.path || '';
  else if (name === 'list_directory') argsStr = args.path || '(CWD)';
  else if (name === 'update_plan') argsStr = (args.plan || []).length + ' steps';
  else if (name === 'git_commit') argsStr = args.message || '';
  else if (name === 'validate_changes') argsStr = args.command || '';
  else if (name === 'list_git_changes') argsStr = args.mode || 'status';
  else if (name === 'grep_search') argsStr = args.pattern || '';
  else argsStr = JSON.stringify(args).slice(0, 100);
  div.innerHTML = '<div class="tool-header running"><span class="tool-icon">' + meta.icon + '</span><span class="tool-label" style="color:' + meta.color + '">' + meta.label + '</span><span class="tool-cmd">' + h(argsStr) + '</span><span class="tool-badge running">Running</span></div><div class="tool-output" style="display:none"></div>';
  messagesEl.appendChild(div);
  scroll();
  commandHistory.push({ name: name, args: args, timestamp: Date.now() });
  renderHistory();
}

function updateToolResult(id, output, success, exitCode, name) {
  var el = document.getElementById('tc-' + id);
  if (!el) return;
  var header = el.querySelector('.tool-header');
  var badge = el.querySelector('.tool-badge');
  var outEl = el.querySelector('.tool-output');
  header.classList.remove('running');
  header.classList.add(success ? 'success' : 'failed');
  badge.className = 'tool-badge ' + (success ? 'success' : 'failed');
  badge.textContent = success ? 'OK' : 'FAIL';
  if (exitCode !== undefined && exitCode !== null) {
    var ec = document.createElement('span');
    ec.className = 'exit-code ' + (success ? 'exit-ok' : 'exit-fail');
    ec.textContent = ' exit:' + exitCode;
    badge.appendChild(ec);
  }
  if (output) {
    outEl.style.display = 'block';
    outEl.textContent = output;
  }
}

function renderPlan() {
  var list = document.getElementById('planList');
  var count = document.getElementById('planCount');
  if (!currentPlan.length) { list.innerHTML = '<div class="plan-empty">No plan yet</div>'; count.textContent = '0'; return; }
  count.textContent = currentPlan.length;
  var statusIcons = { pending: '\u25cb', in_progress: '\u25d0', completed: '\u25cf' };
  var html = '';
  for (var i = 0; i < currentPlan.length; i++) {
    var s = currentPlan[i];
    html += '<div class="plan-item plan-' + (s.status || 'pending') + '"><span class="plan-icon">' + (statusIcons[s.status] || '\u25cb') + '</span><span class="plan-text">' + h(s.step) + '</span></div>';
  }
  list.innerHTML = html;
}

function renderHistory() {
  var list = document.getElementById('historyList');
  if (!commandHistory.length) { list.innerHTML = '<div class="plan-empty">No commands yet</div>'; return; }
  var html = '';
  var recent = commandHistory.slice(-20).reverse();
  for (var i = 0; i < recent.length; i++) {
    var c = recent[i];
    var meta = getToolMeta(c.name);
    var display = c.args.command || c.args.query || c.args.path || c.args.message || c.args.pattern || '';
    html += '<div class="history-item"><span class="tool-icon">' + meta.icon + '</span><span class="history-text">' + h(display.slice(0, 40)) + '</span></div>';
  }
  list.innerHTML = html;
}

function renderSessions() {
  var list = document.getElementById('sessionsList');
  if (!sessions.length) { list.innerHTML = '<div class="plan-empty">No sessions</div>'; return; }
  var html = '';
  for (var i = 0; i < sessions.length; i++) {
    var s = sessions[i];
    var age = Math.floor((Date.now() / 1000 - s.created_at) / 60);
    var ageStr = age < 60 ? age + 'm' : Math.floor(age / 60) + 'h';
    html += '<div class="history-item" onclick="loadSession(\'' + s.id + '\')" style="cursor:pointer"><span class="tool-icon">\ud83d\udcdd</span><span class="history-text">' + s.id.slice(0, 8) + '\u2026 (' + s.messages + ' msgs, ' + ageStr + ' ago)</span></div>';
  }
  list.innerHTML = html;
}

function loadSession(sid) {
  fetch('/api/sessions/load', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sid }),
  }).then(function(resp) { return resp.json(); }).then(function(data) {
    if (data.session && data.session.messages) {
      messagesEl.innerHTML = '';
      for (var i = 0; i < data.session.messages.length; i++) {
        var m = data.session.messages[i];
        if (m.role === 'user' || m.role === 'assistant') addMsg(m.role, m.content);
      }
      addSystemMsg('Loaded session ' + sid.slice(0, 8));
    }
  }).catch(function(e) { addSystemMsg('Failed to load session: ' + e.message); });
}

function scroll() {
  if (!userScrolledUp) chatArea.scrollTop = chatArea.scrollHeight;
}
chatArea.addEventListener('scroll', function() {
  var atBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100;
  userScrolledUp = !atBottom;
});

function showLoading() {
  var div = document.createElement('div');
  div.className = 'loading-dots';
  div.id = 'loadingDots';
  div.innerHTML = '<span></span><span></span><span></span>';
  messagesEl.appendChild(div);
  scroll();
}
function hideLoading() {
  var el = document.getElementById('loadingDots');
  if (el) el.remove();
}

function sendMessage() {
  var text = userInput.value.trim();
  if (!text || isStreaming) return;
  userInput.value = '';
  userInput.style.height = 'auto';
  isStreaming = true;
  sendBtn.disabled = true;
  totalTokens = 0;
  statusDot.className = 'status-dot running';
  addMsg('user', text);
  chatHistory.push({ role: 'user', content: text });
  showLoading();
  userScrolledUp = false;

  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify({ messages: chatHistory, provider: currentProvider, model: currentModel }),
  }).then(function(resp) {
    if (!resp.ok) {
      return resp.json().catch(function() { return { error: 'HTTP ' + resp.status }; }).then(function(err) {
        hideLoading();
        addSystemMsg('Error: ' + (err.error || resp.status));
        isStreaming = false; sendBtn.disabled = false; statusDot.className = 'status-dot';
        throw new Error('HTTP error');
      });
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    var agentDiv = null;
    var contentEl = null;
    var fullText = '';

    function processStream(result) {
      if (result.done) {
        if (agentDiv && !fullText) contentEl.innerHTML = renderMd('');
        isStreaming = false;
        sendBtn.disabled = false;
        statusDot.className = 'status-dot';
        iterBadge.style.display = 'none';
        scroll();
        userInput.focus();
        fetch('/api/sessions').then(function(r) { return r.json(); }).then(function(sd) { sessions = sd.sessions || []; renderSessions(); }).catch(function() {});
        return;
      }
      buf += decoder.decode(result.value, { stream: true });
      var events = buf.split('\n\n');
      buf = events.pop() || '';

      for (var i = 0; i < events.length; i++) {
        var ev = events[i];
        var data = '';
        var lines = ev.split('\n');
        for (var j = 0; j < lines.length; j++) {
          if (lines[j].startsWith('data: ')) data = lines[j].slice(6);
        }
        if (!data) continue;
        try {
          var p = JSON.parse(data);
          switch (p.type) {
            case 'iteration':
              addIterSep(p.data);
              iterBadge.style.display = 'flex';
              iterText.textContent = p.data;
              break;
            case 'token':
              if (!agentDiv) { hideLoading(); agentDiv = addMsg('assistant', '', true); contentEl = agentDiv.querySelector('.msg-content'); }
              fullText += p.data;
              contentEl.innerHTML = renderMd(fullText) + '<span class="cursor"></span>';
              scroll();
              break;
            case 'done':
              if (!agentDiv) { hideLoading(); agentDiv = addMsg('assistant', p.data || fullText); }
              else contentEl.innerHTML = renderMd(p.data || fullText);
              chatHistory.push({ role: 'assistant', content: p.data || fullText });
              break;
            case 'tool_call':
              var tc = typeof p.data === 'string' ? JSON.parse(p.data) : p.data;
              if (!agentDiv) { hideLoading(); agentDiv = addMsg('assistant', '', true); contentEl = agentDiv.querySelector('.msg-content'); }
              addToolCall(tc.id || 'tc-' + Date.now(), tc.name || '', tc.args || {});
              break;
            case 'tool_result':
              var tr = typeof p.data === 'string' ? JSON.parse(p.data) : p.data;
              updateToolResult(tr.id, tr.output || '', tr.success, tr.exit_code, tr.name);
              break;
            case 'plan':
              currentPlan = p.data || [];
              renderPlan();
              break;
            case 'tokens':
              var t = p.data || {};
              totalTokens = (t.prompt || 0) + (t.completion || 0);
              tokenBadge.style.display = 'flex';
              tokenText.textContent = totalTokens.toLocaleString() + ' tok';
              break;
            case 'tokens_final':
              var t2 = p.data || {};
              totalTokens = (t2.prompt || 0) + (t2.completion || 0);
              tokenText.textContent = totalTokens.toLocaleString() + ' tok';
              break;
            case 'session_saved':
              addSystemMsg('Session saved: ' + p.data);
              break;
            case 'error':
              statusDot.className = 'status-dot error';
              if (!agentDiv) { hideLoading(); agentDiv = addMsg('assistant', ''); contentEl = agentDiv.querySelector('.msg-content'); }
              fullText += '\n\n\u26a0\ufe0f ' + p.data;
              contentEl.innerHTML = renderMd(fullText);
              break;
          }
        } catch (e) {}
      }
      return reader.read().then(processStream);
    }
    return reader.read().then(processStream);
  }).catch(function(e) {
    if (e.message !== 'HTTP error') {
      hideLoading();
      statusDot.className = 'status-dot error';
      addSystemMsg('Connection error: ' + e.message);
    }
    isStreaming = false;
    sendBtn.disabled = false;
    statusDot.className = 'status-dot';
    iterBadge.style.display = 'none';
  });
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function sendQuick(text) {
  userInput.value = text;
  sendMessage();
}

document.addEventListener('keydown', function(e) {
  if (e.key === '/' && document.activeElement !== userInput) { e.preventDefault(); userInput.focus(); }
  if (e.key === 'Escape') {
    modelDropdown.classList.remove('show');
    var cwdWrap = document.getElementById('cwdInputWrap');
    if (cwdWrap && cwdWrap.style.display !== 'none') toggleCwdEdit();
  }
});

userInput.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

function loadHistory() {
  try {
    var stored = localStorage.getItem('shellagent_history');
    if (stored) commandHistory = JSON.parse(stored);
    renderHistory();
  } catch (e) {}
}

function saveHistory() {
  try { localStorage.setItem('shellagent_history', JSON.stringify(commandHistory.slice(-100))); } catch (e) {}
}
setInterval(saveHistory, 10000);

init();
