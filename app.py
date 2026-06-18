#!/usr/bin/env python3
"""
ShellAgent v4.0 — Full Agentic AI Agent with Web + File + Shell Tools
Like Codex: uses function calling with shell, web search, web fetch,
file read/write, and directory listing. No command timeout, auto-retry.
Zero external dependencies — Python 3.8+ stdlib only.
"""

import http.server
import json
import os
import sys
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import signal
import traceback
import html as html_mod
import re

# ── Configuration ──────────────────────────────────────────────────────────
PORT          = int(os.environ.get("SHELLAGENT_PORT", "8765"))
HOST          = os.environ.get("SHELLAGENT_HOST", "0.0.0.0")
CWD           = os.environ.get("SHELLAGENT_CWD", os.getcwd())
CMD_TIMEOUT   = int(os.environ.get("SHELLAGENT_CMD_TIMEOUT", "3600"))
MAX_ITERS     = int(os.environ.get("SHELLAGENT_MAX_ITERS", "30"))
WEB_TIMEOUT   = 30
FILE_MAX_READ = 100000
WEB_MAX_LEN   = 8000

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")

DEFAULT_PROVIDER = os.environ.get("SHELLAGENT_PROVIDER", "openai")
DEFAULT_MODEL    = os.environ.get("SHELLAGENT_MODEL", "")

# ── Tool definitions ──────────────────────────────────────────────────────

ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command. Returns stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "working_directory": {"type": "string", "description": "Optional working directory"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. Use for current info, docs, error solutions, API references.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL and return its text content. Use to read docs, blog posts, API refs, or any web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from disk. Returns content as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (absolute or relative)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates dirs if needed. Overwrites existing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (defaults to cwd)"},
                },
            },
        },
    },
]

# ── System prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ShellAgent, an autonomous AI agent with full tool access on the user's machine.

## Tools

- `execute_shell_command` — run any shell command
- `web_search` — search the web for current information
- `web_fetch` — fetch and read any URL's content
- `read_file` — read files on disk
- `write_file` — create or overwrite files
- `list_directory` — explore directory structure

## How you work

1. Analyze the user's request
2. Choose the right tool(s) — you can mix web, file, and shell tools freely
3. If a command fails, diagnose the error and try a different approach
4. When the task is complete, summarize what was done

## Web research workflow

When you need current information (docs, tutorials, error fixes, API references):
1. `web_search` with a targeted query
2. Review the results for the most relevant URLs
3. `web_fetch` on those URLs to get full content
4. Use the information to complete the task

## Rules

- Execute everything immediately — no confirmation needed
- Use any combination of tools in any order
- If something fails, retry with a different approach
- Read files before modifying them
- For complex tasks, break into steps
- Be thorough but efficient"""

# ── Provider definitions ───────────────────────────────────────────────────

PROVIDERS = {
    "openai": {
        "name": "OpenAI", "url": "https://api.openai.com/v1/chat/completions",
        "env_key": "OPENAI_API_KEY",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o3-mini", "o4-mini"],
        "supports_tools": True, "needs_key": True,
    },
    "nvidia": {
        "name": "NVIDIA NIM", "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "env_key": "NVIDIA_API_KEY",
        "models": [
            "meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct", "meta/llama-3.1-70b-instruct",
            "nvidia/llama-3.3-nemotron-super-49b-v1", "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "mistralai/mistral-large-2-instruct", "mistralai/codestral-2405",
            "google/gemma-2-27b-it", "deepseek-ai/deepseek-r1",
        ],
        "supports_tools": True, "needs_key": True,
    },
    "ollama": {
        "name": "Ollama", "url": None, "env_key": "OLLAMA_API_KEY",
        "models": [], "supports_tools": True, "needs_key": False,
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────

def get_system_context():
    ctx = f"Working directory: {CWD}\nOS: {sys.platform}\nPython: {sys.version}\n"
    for cmd_args, parser in [
        (["uname", "-a"], lambda t, _: f"System: {t.strip()}"),
        (["df", "-h", "/"], _parse_df), (["free", "-h"], _parse_free),
    ]:
        try:
            r = subprocess.run(cmd_args, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ctx += parser(r.stdout, r.stderr) + "\n"
        except Exception:
            pass
    return ctx

def _parse_df(t, _):
    lines = t.strip().split("\n")
    if len(lines) > 1:
        p = lines[1].split()
        if len(p) >= 5: return f"Disk: {p[2]} used / {p[1]} total ({p[4]})"
    return ""

def _parse_free(t, _):
    lines = t.strip().split("\n")
    if len(lines) > 1:
        p = lines[1].split()
        if len(p) >= 3: return f"Memory: {p[2]} used / {p[1]} total"
    return ""

def get_api_key(provider):
    return os.environ.get(PROVIDERS.get(provider, {}).get("env_key", ""), "")

def get_model(provider, model_override=""):
    if model_override: return model_override
    if DEFAULT_MODEL and provider == DEFAULT_PROVIDER: return DEFAULT_MODEL
    models = PROVIDERS.get(provider, {}).get("models", [])
    return models[0] if models else ""

def get_provider_url(provider):
    if provider == "ollama": return f"{OLLAMA_HOST.rstrip('/')}/v1/chat/completions"
    return PROVIDERS.get(provider, {}).get("url", "")

# ── Tool implementations ──────────────────────────────────────────────────

def execute_shell_command(command, working_directory=None):
    cwd = working_directory or CWD
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=CMD_TIMEOUT, cwd=cwd,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"}
        )
        out = (r.stdout or "").strip()
        if r.stderr: out += ("\n" if out else "") + f"[stderr] {r.stderr.strip()}"
        out += f"\n[exit code: {r.returncode}]"
        return {"output": out.strip() or "[no output]", "success": r.returncode == 0, "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"output": f"[timeout after {CMD_TIMEOUT}s]", "success": False, "exit_code": -1}
    except Exception as e:
        return {"output": f"[error: {e}]", "success": False, "exit_code": -1}

def web_search(query):
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html",
        })
        resp = urllib.request.urlopen(req, timeout=WEB_TIMEOUT)
        page = resp.read().decode("utf-8", errors="replace")

        results = []
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:td|span|div)', page, re.DOTALL):
            href, title, snippet = m.group(1), _strip_html(m.group(2)), _strip_html(m.group(3))
            if "uddg=" in href:
                m2 = re.search(r'uddg=([^&]+)', href)
                if m2: href = urllib.parse.unquote(m2.group(1))
            if title.strip():
                results.append({"title": title.strip(), "url": href.strip(), "snippet": snippet.strip()})
            if len(results) >= 8: break

        if not results:
            return {"output": f"No results for: {query}", "success": True}

        output = f"Search results for: {query}\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n\n"
        return {"output": output.strip(), "success": True}
    except Exception as e:
        return {"output": f"Search error: {e}", "success": False}

def web_fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        resp = urllib.request.urlopen(req, timeout=WEB_TIMEOUT)
        raw = resp.read()
        try: import gzip; raw = gzip.decompress(raw)
        except Exception: pass
        page = raw.decode("utf-8", errors="replace")
        text = _extract_text(page)
        if len(text) > WEB_MAX_LEN:
            text = text[:WEB_MAX_LEN] + f"\n\n[truncated — {len(text)} chars total]"
        return {"output": f"Content of {url}:\n\n{text}", "success": True}
    except Exception as e:
        return {"output": f"Fetch error ({url}): {e}", "success": False}

def read_file(path):
    try:
        fpath = os.path.expanduser(path)
        if not os.path.isabs(fpath): fpath = os.path.join(CWD, fpath)
        if not os.path.exists(fpath): return {"output": f"Not found: {path}", "success": False}
        sz = os.path.getsize(fpath)
        with open(fpath, "r", errors="replace") as f:
            content = f.read(FILE_MAX_READ)
        if sz > FILE_MAX_READ: content += f"\n\n[truncated — {sz} bytes total]"
        return {"output": content or "[empty file]", "success": True}
    except Exception as e:
        return {"output": f"Read error: {e}", "success": False}

def write_file(path, content):
    try:
        fpath = os.path.expanduser(path)
        if not os.path.isabs(fpath): fpath = os.path.join(CWD, fpath)
        os.makedirs(os.path.dirname(fpath) or ".", exist_ok=True)
        with open(fpath, "w") as f: f.write(content)
        return {"output": f"Written {len(content)} bytes to {fpath}", "success": True}
    except Exception as e:
        return {"output": f"Write error: {e}", "success": False}

def list_directory(path="."):
    try:
        dpath = os.path.expanduser(path)
        if not os.path.isabs(dpath): dpath = os.path.join(CWD, dpath)
        if not os.path.isdir(dpath): return {"output": f"Not a directory: {path}", "success": False}
        entries = []
        for name in sorted(os.listdir(dpath)):
            full = os.path.join(dpath, name)
            is_dir = os.path.isdir(full)
            try: size = os.path.getsize(full) if not is_dir else 0
            except Exception: size = 0
            entries.append(f"{'📁' if is_dir else '📄'} {name}{'/' if is_dir else ''}  {_fmt_size(size) if not is_dir else ''}")
        return {"output": f"Contents of {dpath} ({len(entries)} items):\n\n" + "\n".join(entries), "success": True}
    except Exception as e:
        return {"output": f"List error: {e}", "success": False}

def _fmt_size(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024: return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

def _strip_html(text):
    return re.sub(r'\s+', ' ', html_mod.unescape(re.sub(r'<[^>]+>', '', text))).strip()

def _extract_text(page):
    for tag in ['script', 'style', 'nav', 'footer', 'header']:
        page = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', page, flags=re.DOTALL | re.IGNORECASE)
    page = re.sub(r'<br\s*/?>', '\n', page, flags=re.IGNORECASE)
    page = re.sub(r'<p[^>]*>', '\n\n', page, flags=re.IGNORECASE)
    page = re.sub(r'<h[1-6][^>]*>', '\n\n## ', page, flags=re.IGNORECASE)
    page = re.sub(r'</h[1-6]>', '\n', page, flags=re.IGNORECASE)
    page = re.sub(r'<li[^>]*>', '\n- ', page, flags=re.IGNORECASE)
    page = re.sub(r'<pre[^>]*>', '\n```\n', page, flags=re.IGNORECASE)
    page = re.sub(r'</pre>', '\n```\n', page, flags=re.IGNORECASE)
    page = re.sub(r'<code[^>]*>', '`', page, flags=re.IGNORECASE)
    page = re.sub(r'</code>', '`', page, flags=re.IGNORECASE)
    page = re.sub(r'<[^>]+>', '', page)
    page = html_mod.unescape(page)
    page = re.sub(r'\n{3,}', '\n\n', page)
    page = re.sub(r'[ \t]+', ' ', page)
    return '\n'.join(l.rstrip() for l in page.split('\n')).strip()

# ── Tool dispatcher ────────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "execute_shell_command": lambda a: execute_shell_command(a.get("command", ""), a.get("working_directory")),
    "web_search":            lambda a: web_search(a.get("query", "")),
    "web_fetch":             lambda a: web_fetch(a.get("url", "")),
    "read_file":             lambda a: read_file(a.get("path", ".")),
    "write_file":            lambda a: write_file(a.get("path", ""), a.get("content", "")),
    "list_directory":        lambda a: list_directory(a.get("path", ".")),
}

# ── LLM streaming ─────────────────────────────────────────────────────────

def call_llm_stream(provider, messages, model="", tools=None):
    model = get_model(provider, model)
    api_key = get_api_key(provider)
    url = get_provider_url(provider)
    payload = {"model": model, "messages": messages, "stream": True, "temperature": 0.1}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if provider != "ollama" or api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers)
    return urllib.request.urlopen(req, timeout=600 if provider == "ollama" else 300)

def iter_openai_stream(resp):
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "): continue
        data = line[6:]
        if data == "[DONE]": break
        try:
            chunk = json.loads(data)
            choice = chunk.get("choices", [{}])[0]
            yield {"delta": choice.get("delta", {}), "finish_reason": choice.get("finish_reason")}
        except (json.JSONDecodeError, KeyError, IndexError): continue

def iter_ollama_stream(resp):
    buf = b""
    for chunk in resp:
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
                msg = obj.get("message", {})
                delta = {}
                if msg.get("content"): delta["content"] = msg["content"]
                if msg.get("tool_calls"): delta["tool_calls"] = msg["tool_calls"]
                yield {"delta": delta, "finish_reason": "stop" if obj.get("done") else None}
            except (json.JSONDecodeError, KeyError): continue

# ── Ollama ─────────────────────────────────────────────────────────────────

def discover_ollama_models():
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_HOST.rstrip('/')}/api/tags", timeout=5)
        data = json.loads(resp.read().decode())
        PROVIDERS["ollama"]["models"] = sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
        return PROVIDERS["ollama"]["models"]
    except Exception: return []

def discover_ollama_running():
    try: return urllib.request.urlopen(f"{OLLAMA_HOST.rstrip('/')}/api/tags", timeout=3).status == 200
    except Exception: return False

# ── Agentic loop ───────────────────────────────────────────────────────────

class AgenticLoop:
    def __init__(self, handler, provider, model):
        self.handler = handler
        self.provider = provider
        self.model = model
        self.messages = []
        self.iteration = 0

    def run(self, user_messages):
        sys_ctx = get_system_context()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}] + list(user_messages)

        while self.iteration < MAX_ITERS:
            self.iteration += 1
            self.handler._sse("iteration", str(self.iteration))
            try:
                resp = call_llm_stream(self.provider, self.messages, self.model, tools=ALL_TOOLS)
            except Exception as e:
                self.handler._sse("error", f"LLM call failed: {e}"); return

            full_content = ""
            tool_calls_raw = {}
            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream

            for chunk in iter_fn(resp):
                delta = chunk.get("delta", {})
                content = delta.get("content", "")
                if content:
                    full_content += content
                    self.handler._sse("token", content)
                for tc in delta.get("tool_calls", []):
                    if not isinstance(tc, dict): continue
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {"id": tc.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}
                    entry = tool_calls_raw[idx]
                    if tc.get("id"): entry["id"] = tc["id"]
                    func = tc.get("function", {})
                    if func.get("name"): entry["function"]["name"] = func["name"]
                    if func.get("arguments"): entry["function"]["arguments"] += func["arguments"]

            assistant_msg = {"role": "assistant", "content": full_content or None}
            if tool_calls_raw:
                assistant_msg["tool_calls"] = [tool_calls_raw[k] for k in sorted(tool_calls_raw.keys())]
            self.messages.append(assistant_msg)

            if not tool_calls_raw:
                self.handler._sse("done", full_content); return

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                try: args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError: args = {}

                self.handler._sse("tool_call", {"id": tc.get("id", ""), "name": func_name, "args": args})
                dispatcher = TOOL_DISPATCH.get(func_name)
                result = dispatcher(args) if dispatcher else {"output": f"Unknown tool: {func_name}", "success": False}

                self.handler._sse("tool_result", {
                    "id": tc.get("id", ""), "name": func_name,
                    "output": result["output"], "success": result.get("success", False),
                    "exit_code": result.get("exit_code"),
                })
                self.messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result["output"]})

        self.handler._sse("done", f"\n\n[Reached maximum iterations ({MAX_ITERS})]")

    def run_fallback(self, user_messages):
        sys_ctx = get_system_context()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}] + list(user_messages)
        while self.iteration < MAX_ITERS:
            self.iteration += 1
            self.handler._sse("iteration", str(self.iteration))
            try: resp = call_llm_stream(self.provider, self.messages, self.model)
            except Exception as e: self.handler._sse("error", f"LLM call failed: {e}"); return
            full_content = ""
            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream
            for chunk in iter_fn(resp):
                content = chunk.get("delta", {}).get("content", "")
                if content:
                    full_content += content
                    self.handler._sse("token", content)
            self.messages.append({"role": "assistant", "content": full_content})
            commands = _parse_code_blocks(full_content)
            if not commands: self.handler._sse("done", full_content); return
            results_text = ""
            for cmd in commands:
                self.handler._sse("tool_call", {"id": f"fb-{self.iteration}", "name": "execute_shell_command", "args": {"command": cmd}})
                result = execute_shell_command(cmd)
                self.handler._sse("tool_result", {"id": f"fb-{self.iteration}", "name": "execute_shell_command", "output": result["output"], "success": result["success"], "exit_code": result.get("exit_code")})
                results_text += f"$ {cmd}\n{result['output']}\n\n"
            self.messages.append({"role": "user", "content": f"Command results:\n{results_text}\nContinue. If failed, fix and retry. If done, summarize."})
        self.handler._sse("done", f"\n\n[Reached maximum iterations ({MAX_ITERS})]")

def _parse_code_blocks(text):
    cmds, in_block, cur = [], False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```bash") or s.startswith("```sh"): in_block, cur = True, []; continue
        if s == "```" and in_block:
            if cur: cmds.append("\n".join(cur))
            in_block = False; continue
        if in_block: cur.append(line)
    return cmds

# ── HTTP Server ────────────────────────────────────────────────────────────

class AgentHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_file("templates/index.html", "text/html")
        elif path.startswith("/static/"):
            ct = {"css": "text/css", "js": "text/javascript"}.get(path.rsplit(".", 1)[-1] if "." in path else "", "application/octet-stream")
            self._serve_file(path[1:], ct)
        elif path == "/api/health":
            self.send_json({"status": "ok", "version": "4.0", "tools": [t["function"]["name"] for t in ALL_TOOLS]})
        elif path == "/api/providers":
            result = {}
            for k, v in PROVIDERS.items():
                models = v["models"] if k != "ollama" else discover_ollama_models()
                result[k] = {"name": v["name"], "models": models, "needs_key": v["needs_key"], "key_set": bool(get_api_key(k)), "supports_tools": v.get("supports_tools", False)}
            self.send_json(result)
        elif path == "/api/system":
            self.send_json({"context": get_system_context()})
        else: self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chat": self._handle_chat()
        elif path == "/api/execute":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) if self.headers.get("Content-Length") else b"{}")
            self.send_json(execute_shell_command(body.get("command", ""), body.get("cwd")))
        else: self.send_error(404)

    def _serve_file(self, fp, ct):
        fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fp)
        try:
            with open(fpath, "rb") as f: data = f.read()
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        except FileNotFoundError: self.send_error(404)

    def _handle_chat(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) if self.headers.get("Content-Length") else b"{}")
        messages, provider, model = body.get("messages", []), body.get("provider", DEFAULT_PROVIDER), body.get("model", "")
        if provider not in PROVIDERS: self.send_json({"error": f"unknown provider: {provider}"}, 400); return
        if PROVIDERS[provider]["needs_key"] and not get_api_key(provider):
            self.send_json({"error": f"Set {PROVIDERS[provider]['env_key']}"}, 400); return

        self.send_response(200)
        for h, v in [("Content-Type", "text/event-stream"), ("Cache-Control", "no-cache"), ("Connection", "keep-alive"), ("Access-Control-Allow-Origin", "*")]:
            self.send_header(h, v)
        self.end_headers()

        try:
            loop = AgenticLoop(self, provider, model)
            if PROVIDERS.get(provider, {}).get("supports_tools"): loop.run(messages)
            else: loop.run_fallback(messages)
        except Exception as e:
            self._sse("error", f"Fatal: {e}")
        finally:
            try: self.wfile.write(b""); self.wfile.flush()
            except Exception: pass

    def _sse(self, event, data):
        msg = f"event: {event}\ndata: {json.dumps({'type': event, 'data': data})}\n\n"
        try: self.wfile.write(msg.encode()); self.wfile.flush()
        except Exception: pass

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    ollama_info = f"✓ {len(discover_ollama_models())} model(s)" if discover_ollama_running() else "✗ not running"
    tools_str = ", ".join(t["function"]["name"] for t in ALL_TOOLS)
    print(f"""
╔═══════════════════════════════════════════════════════╗
║             ShellAgent v4.0                           ║
║  Full Agent — Shell + Web + Files + Search           ║
╠═══════════════════════════════════════════════════════╣
║  Dashboard : http://localhost:{PORT:<25}║
║  Tools     : {tools_str:<42}║
╠═══════════════════════════════════════════════════════╣
║  Providers                                            ║
║  ├─ OpenAI  : {"✓ set" if OPENAI_API_KEY else "✗ not set":<42}║
║  ├─ NVIDIA  : {"✓ set" if NVIDIA_API_KEY else "✗ not set":<42}║
║  └─ Ollama  : {ollama_info:<42}║
╚═══════════════════════════════════════════════════════╝
""")
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    http.server.HTTPServer((HOST, PORT), AgentHandler).serve_forever()

if __name__ == "__main__":
    main()
