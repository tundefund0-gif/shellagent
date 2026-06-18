#!/usr/bin/env python3
"""
ShellAgent v2.0 — AI Shell Agent with Multi-Provider Support
Supports: OpenAI, NVIDIA NIM, Ollama (local + remote)
Zero external dependencies — Python 3.8+ stdlib only.
32-bit and 64-bit systems.
"""

import http.server
import json
import os
import sys
import subprocess
import threading
import urllib.request
import urllib.error
import signal
import re

# ── Configuration ──────────────────────────────────────────────────────────
PORT          = int(os.environ.get("SHELLAGENT_PORT", "8765"))
HOST          = os.environ.get("SHELLAGENT_HOST", "0.0.0.0")
SHELL_TIMEOUT = int(os.environ.get("SHELLAGENT_TIMEOUT", "60"))
CWD           = os.environ.get("SHELLAGENT_CWD", os.getcwd())

# Provider keys
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")

# Default provider / model
DEFAULT_PROVIDER = os.environ.get("SHELLAGENT_PROVIDER", "openai")
DEFAULT_MODEL    = os.environ.get("SHELLAGENT_MODEL", "")

SYSTEM_PROMPT = """You are ShellAgent, an autonomous AI shell agent running on the user's machine.
You can execute ANY shell command immediately — no confirmation needed.

Rules:
1. When you want to run a command, wrap it in ```bash\n...\n``` blocks
2. You can include multiple code blocks — each will be executed automatically
3. Always explain what each command does briefly
4. If a command fails, try to fix it and re-run
5. You have full shell access — use it confidently
6. Be concise. Show results. Move on.
7. For complex tasks, break them into sequential commands

The system will auto-detect commands and run them. No approval needed."""

# ── Provider definitions ───────────────────────────────────────────────────
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "env_key": "OPENAI_API_KEY",
        "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "o3", "o3-mini", "o4-mini",
        ],
        "stream_format": "openai",
        "needs_key": True,
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "env_key": "NVIDIA_API_KEY",
        "models": [
            "meta/llama-3.3-70b-instruct",
            "meta/llama-3.1-8b-instruct",
            "meta/llama-3.1-70b-instruct",
            "nvidia/llama-3.3-nemotron-super-49b-v1",
            "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "mistralai/mistral-large-2-instruct",
            "mistralai/codestral-2405",
            "google/gemma-2-27b-it",
            "deepseek-ai/deepseek-r1",
        ],
        "stream_format": "openai",
        "needs_key": True,
    },
    "ollama": {
        "name": "Ollama",
        "url": None,  # dynamic
        "env_key": "OLLAMA_API_KEY",
        "models": [],  # discovered at runtime
        "stream_format": "ollama",
        "needs_key": False,
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────

def get_system_context():
    ctx = f"Working directory: {CWD}\nOS: {sys.platform}\nPython: {sys.version}\n"
    for cmd, label in [
        (["uname", "-a"], "System"),
        (["df", "-h", "/"], None),
        (["free", "-h"], None),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                if label:
                    ctx += f"{label}: {r.stdout.strip()}\n"
                else:
                    lines = r.stdout.strip().split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        if label is None and cmd[0] == "df" and len(parts) >= 4:
                            ctx += f"Disk: {parts[2]} used / {parts[1]} total ({parts[4]})\n"
                        elif cmd[0] == "free" and len(parts) >= 3:
                            ctx += f"Memory: {parts[2]} used / {parts[1]} total\n"
        except Exception:
            pass
    return ctx


def get_api_key(provider):
    info = PROVIDERS.get(provider, {})
    env = info.get("env_key", "")
    return os.environ.get(env, "")


def get_model(provider, model_override=""):
    if model_override:
        return model_override
    if DEFAULT_MODEL and provider == DEFAULT_PROVIDER:
        return DEFAULT_MODEL
    info = PROVIDERS.get(provider, {})
    models = info.get("models", [])
    return models[0] if models else ""


def get_provider_url(provider):
    if provider == "ollama":
        base = OLLAMA_HOST.rstrip("/")
        return f"{base}/v1/chat/completions"
    return PROVIDERS.get(provider, {}).get("url", "")


def parse_commands(text):
    commands = []
    in_block = False
    current = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```bash") or stripped.startswith("```sh") or stripped.startswith("```shell"):
            in_block = True
            current = []
            continue
        if stripped == "```" and in_block:
            if current:
                commands.append("\n".join(current))
            in_block = False
            current = []
            continue
        if in_block:
            current.append(line)
    return commands


def execute_command(cmd, cwd=None, timeout=None):
    timeout = timeout or SHELL_TIMEOUT
    cwd = cwd or CWD
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"}
        )
        out = r.stdout or ""
        if r.stderr:
            out += ("\n" if out else "") + r.stderr
        if r.returncode != 0:
            out += f"\n[exit code: {r.returncode}]"
        return out.strip() or "[no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as e:
        return f"[error: {e}]"


# ── LLM call (streaming) ──────────────────────────────────────────────────

def call_llm_stream(provider, messages, model=""):
    model = get_model(provider, model)
    api_key = get_api_key(provider)
    url = get_provider_url(provider)

    if provider == "ollama":
        return call_ollama_stream(url, messages, model, api_key)
    elif provider == "nvidia":
        return call_openai_compat_stream(url, messages, model, api_key)
    else:
        return call_openai_compat_stream(url, messages, model, api_key)


def call_openai_compat_stream(url, messages, model, api_key):
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
        "max_tokens": 4096,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    return urllib.request.urlopen(req, timeout=180)


def call_ollama_stream(url, messages, model, api_key):
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=payload, headers=headers)
    return urllib.request.urlopen(req, timeout=300)


def iter_openai_stream(resp):
    """Yields text tokens from OpenAI-compatible SSE stream."""
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content
        except (json.JSONDecodeError, KeyError, IndexError):
            continue


def iter_ollama_stream(resp):
    """Yields text tokens from Ollama NDJSON stream."""
    buf = b""
    for chunk in resp:
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
                text = obj.get("message", {}).get("content", "")
                if text:
                    yield text
            except (json.JSONDecodeError, KeyError):
                continue


def iter_stream(provider, resp):
    if provider == "ollama":
        return iter_ollama_stream(resp)
    return iter_openai_stream(resp)


# ── Ollama model discovery ────────────────────────────────────────────────

def discover_ollama_models():
    base = OLLAMA_HOST.rstrip("/")
    url = f"{base}/api/tags"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if name:
                models.append(name)
        PROVIDERS["ollama"]["models"] = sorted(models)
        return models
    except Exception:
        return []


def discover_ollama_running():
    base = OLLAMA_HOST.rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/api/tags")
        resp = urllib.request.urlopen(req, timeout=3)
        return resp.status == 200
    except Exception:
        return False


# ── HTTP Server ────────────────────────────────────────────────────────────

class AgentHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_cors(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_cors()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_file("templates/index.html", "text/html")
        elif path.startswith("/static/"):
            ct_map = {"css": "text/css", "js": "text/javascript", "png": "image/png", "svg": "image/svg+xml"}
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            self._serve_file(path[1:], ct_map.get(ext, "application/octet-stream"))
        elif path == "/api/health":
            self.send_json({
                "status": "ok",
                "providers": {
                    k: {
                        "name": v["name"],
                        "key_set": bool(get_api_key(k)),
                        "models": v["models"][:5],
                    }
                    for k, v in PROVIDERS.items()
                },
                "ollama_running": discover_ollama_running(),
            })
        elif path == "/api/providers":
            result = {}
            for k, v in PROVIDERS.items():
                models = v["models"]
                if k == "ollama":
                    models = discover_ollama_models()
                result[k] = {
                    "name": v["name"],
                    "models": models,
                    "needs_key": v["needs_key"],
                    "key_set": bool(get_api_key(k)),
                }
            self.send_json(result)
        elif path == "/api/ollama/models":
            models = discover_ollama_models()
            self.send_json({"models": models, "host": OLLAMA_HOST})
        elif path == "/api/system":
            self.send_json({"context": get_system_context()})
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/chat":
            self._handle_chat()
        elif path == "/api/execute":
            self._handle_execute()
        elif path == "/api/providers":
            self._handle_set_provider()
        else:
            self.send_error(404)

    def _serve_file(self, filepath, content_type):
        fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _handle_execute(self):
        body = self._read_body()
        cmd = body.get("command", "")
        if not cmd:
            self.send_json({"error": "no command"}, 400)
            return
        output = execute_command(cmd, body.get("cwd"), body.get("timeout"))
        self.send_json({"output": output})

    def _handle_set_provider(self):
        body = self._read_body()
        provider = body.get("provider", DEFAULT_PROVIDER)
        model = body.get("model", "")
        if provider not in PROVIDERS:
            self.send_json({"error": f"unknown provider: {provider}"}, 400)
            return
        self.send_json({"provider": provider, "model": model})

    def _handle_chat(self):
        body = self._read_body()
        messages  = body.get("messages", [])
        provider  = body.get("provider", DEFAULT_PROVIDER)
        model     = body.get("model", "")
        auto_exec = body.get("auto_execute", True)

        if provider not in PROVIDERS:
            self.send_json({"error": f"unknown provider: {provider}"}, 400)
            return

        key = get_api_key(provider)
        if PROVIDERS[provider]["needs_key"] and not key:
            env = PROVIDERS[provider]["env_key"]
            self.send_json({"error": f"Set {env} environment variable"}, 400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        sys_ctx = get_system_context()
        full_messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}
        ] + messages

        full_text = ""
        all_commands = []
        all_outputs = []

        try:
            resp = call_llm_stream(provider, full_messages, model)

            for token in iter_stream(provider, resp):
                full_text += token
                self._sse("token", token)

            self._sse("done", full_text)

            if auto_exec and full_text:
                cmds = parse_commands(full_text)
                for cmd in cmds:
                    all_commands.append(cmd)
                    self._sse("executing", cmd)
                    output = execute_command(cmd)
                    all_outputs.append(output)
                    self._sse("output", output)

                # Feed results back for summary if there were commands
                if all_commands:
                    results_text = ""
                    for c, o in zip(all_commands, all_outputs):
                        results_text += f"$ {c}\n{o}\n\n"
                    follow_up = [
                        *full_messages,
                        {"role": "assistant", "content": full_text},
                        {"role": "user", "content": f"Command results:\n{results_text}\nProvide a brief summary of the output."}
                    ]
                    try:
                        resp2 = call_llm_stream(provider, follow_up, model)
                        summary = ""
                        for token in iter_stream(provider, resp2):
                            summary += token
                            self._sse("summary_token", token)
                        self._sse("summary_done", summary)
                    except Exception:
                        pass

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            self._sse("error", f"API error {e.code}: {err_body[:500]}")
        except urllib.error.URLError as e:
            self._sse("error", f"Connection error: {str(e)}")
        except Exception as e:
            self._sse("error", str(e))
        finally:
            try:
                self.wfile.write(b"")
                self.wfile.flush()
            except Exception:
                pass

    def _sse(self, event, data):
        payload = json.dumps({"type": event, "data": data})
        msg = f"event: {event}\ndata: {payload}\n\n"
        try:
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    # Discover Ollama models on startup
    if discover_ollama_running():
        discover_ollama_models()
        ollama_count = len(PROVIDERS["ollama"]["models"])
        ollama_info = f"✓ {ollama_count} model(s) found"
    else:
        ollama_info = "✗ not running"

    print(f"""
╔═══════════════════════════════════════════════════════╗
║              ShellAgent v2.0                          ║
║      AI Shell Agent — Multi-Provider                  ║
╠═══════════════════════════════════════════════════════╣
║  Dashboard : http://localhost:{PORT:<25}║
║  Platform  : {sys.platform:<40}║
╠═══════════════════════════════════════════════════════╣
║  Providers                                           ║
║  ├─ OpenAI   : {"✓ key set" if OPENAI_API_KEY else "✗ no key":<40}║
║  ├─ NVIDIA   : {"✓ key set" if NVIDIA_API_KEY else "✗ no key":<40}║
║  └─ Ollama   : {ollama_info:<40}║
╚═══════════════════════════════════════════════════════╝
""")
    if not any([OPENAI_API_KEY, NVIDIA_API_KEY, OLLAMA_HOST]):
        print("⚠  Set at least one provider key. Examples:")
        print("   export OPENAI_API_KEY='sk-...'")
        print("   export NVIDIA_API_KEY='nvapi-...'")
        print("   export OLLAMA_HOST='http://localhost:11434'\n")

    def shutdown(sig, frame):
        print("\nShutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server = http.server.HTTPServer((HOST, PORT), AgentHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
