#!/usr/bin/env python3
"""
ShellAgent v3.0 — Agentic AI Shell Agent
Tool/function-calling architecture (like Codex), no command timeout,
automatic retry on failure, multi-provider support.
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
import time
import traceback

# ── Configuration ──────────────────────────────────────────────────────────
PORT          = int(os.environ.get("SHELLAGENT_PORT", "8765"))
HOST          = os.environ.get("SHELLAGENT_HOST", "0.0.0.0")
CWD           = os.environ.get("SHELLAGENT_CWD", os.getcwd())
CMD_TIMEOUT   = int(os.environ.get("SHELLAGENT_CMD_TIMEOUT", "3600"))
MAX_ITERS     = int(os.environ.get("SHELLAGENT_MAX_ITERS", "30"))
MAX_RETRIES   = int(os.environ.get("SHELLAGENT_MAX_RETRIES", "3"))

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")

DEFAULT_PROVIDER = os.environ.get("SHELLAGENT_PROVIDER", "openai")
DEFAULT_MODEL    = os.environ.get("SHELLAGENT_MODEL", "")

# ── Tool definition (OpenAI function-calling schema) ───────────────────────
SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_shell_command",
        "description": (
            "Execute a shell command on the user's machine. "
            "Returns stdout, stderr, and exit code. "
            "Use this for ANY shell operation: reading files, installing packages, "
            "running programs, checking system state, deploying, compiling, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute. Use full paths when possible. Supports pipes, redirects, &&, ||, etc."
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional working directory. Defaults to the current directory."
                },
            },
            "required": ["command"],
        },
    },
}

# ── System prompt ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are ShellAgent, an autonomous AI coding agent running directly on the user's machine.

You have a tool called `execute_shell_command` that runs shell commands and returns the output.

## How you work

1. Analyze the user's request
2. Decide which command(s) to run
3. Call `execute_shell_command` with the command
4. Review the output carefully
5. If the command failed or the output isn't what you expected:
   - Diagnose the error from stdout/stderr/exit code
   - Try a different approach or fix the command
   - Call `execute_shell_command` again with the corrected command
6. When the task is complete, summarize what was done and the results

## Rules

- Execute commands immediately — no confirmation needed
- You can call `execute_shell_command` multiple times in sequence
- If a command fails, ALWAYS try to fix it and retry (up to 3 attempts)
- For complex tasks, break them into smaller commands and execute them one by one
- Always check command output before moving to the next step
- If you need to install something, check what package manager is available first
- Use `working_directory` when you need to run commands in a specific directory
- Be thorough but efficient — get the job done
- After completing the task, give a brief summary of what was done

## Error recovery

When a command fails:
1. Read the error message carefully
2. Common fixes: missing packages (install them), wrong path (find the right one),
   permission issues (try with appropriate flags), syntax errors (fix the command)
3. Try the fixed command
4. If it still fails after 3 attempts, explain what went wrong and suggest alternatives"""


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
        "supports_tools": True,
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
        "supports_tools": True,
        "needs_key": True,
    },
    "ollama": {
        "name": "Ollama",
        "url": None,
        "env_key": "OLLAMA_API_KEY",
        "models": [],
        "supports_tools": True,
        "needs_key": False,
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────

def get_system_context():
    ctx = f"Working directory: {CWD}\nOS: {sys.platform}\nPython: {sys.version}\n"
    for cmd_args, parser in [
        (["uname", "-a"], lambda lines, _: f"System: {lines.strip()}"),
        (["df", "-h", "/"], lambda lines, _: _parse_df(lines)),
        (["free", "-h"], lambda lines, _: _parse_free(lines)),
    ]:
        try:
            r = subprocess.run(cmd_args, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ctx += parser(r.stdout, r.stderr) + "\n"
        except Exception:
            pass
    return ctx


def _parse_df(text):
    lines = text.strip().split("\n")
    if len(lines) > 1:
        parts = lines[1].split()
        if len(parts) >= 5:
            return f"Disk: {parts[2]} used / {parts[1]} total ({parts[4]})"
    return ""


def _parse_free(text):
    lines = text.strip().split("\n")
    if len(lines) > 1:
        parts = lines[1].split()
        if len(parts) >= 3:
            return f"Memory: {parts[2]} used / {parts[1]} total"
    return ""


def get_api_key(provider):
    env = PROVIDERS.get(provider, {}).get("env_key", "")
    return os.environ.get(env, "")


def get_model(provider, model_override=""):
    if model_override:
        return model_override
    if DEFAULT_MODEL and provider == DEFAULT_PROVIDER:
        return DEFAULT_MODEL
    models = PROVIDERS.get(provider, {}).get("models", [])
    return models[0] if models else ""


def get_provider_url(provider):
    if provider == "ollama":
        return f"{OLLAMA_HOST.rstrip('/')}/v1/chat/completions"
    return PROVIDERS.get(provider, {}).get("url", "")


def execute_command(cmd, cwd=None):
    cwd = cwd or CWD
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=CMD_TIMEOUT, cwd=cwd,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"}
        )
        stdout = r.stdout or ""
        stderr = r.stderr or ""
        exit_code = r.returncode
        return {
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exit_code": exit_code,
            "success": exit_code == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {CMD_TIMEOUT}s",
            "exit_code": -1,
            "success": False,
            "timed_out": True,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "success": False,
        }


# ── LLM streaming (raw) ───────────────────────────────────────────────────

def call_llm_raw(provider, messages, model="", tools=None):
    """Non-streaming call that returns full response JSON. Used for tool-calling loop."""
    model = get_model(provider, model)
    api_key = get_api_key(provider)
    url = get_provider_url(provider)

    payload = {"model": model, "messages": messages, "temperature": 0.1}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    if provider == "ollama":
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    else:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    req = urllib.request.Request(url, data=data, headers=headers)
    resp = urllib.request.urlopen(req, timeout=300)
    body = resp.read().decode("utf-8")
    return json.loads(body)


def call_llm_stream(provider, messages, model="", tools=None):
    """Streaming call. Returns the HTTP response for token-by-token reading."""
    model = get_model(provider, model)
    api_key = get_api_key(provider)
    url = get_provider_url(provider)

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if provider != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, headers=headers)
    timeout = 600 if provider == "ollama" else 300
    return urllib.request.urlopen(req, timeout=timeout)


def iter_openai_stream(resp):
    """Yields chunks from OpenAI-compatible SSE. Each chunk is a dict."""
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            choice = chunk.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            finish = choice.get("finish_reason")
            yield {"delta": delta, "finish_reason": finish}
        except (json.JSONDecodeError, KeyError, IndexError):
            continue


def iter_ollama_stream(resp):
    """Yields chunks from Ollama NDJSON stream."""
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
                msg = obj.get("message", {})
                text = msg.get("content", "")
                tool_calls_raw = msg.get("tool_calls", [])
                finish = "stop" if obj.get("done") else None
                delta = {}
                if text:
                    delta["content"] = text
                if tool_calls_raw:
                    delta["tool_calls"] = tool_calls_raw
                yield {"delta": delta, "finish_reason": finish}
            except (json.JSONDecodeError, KeyError):
                continue


# ── Ollama model discovery ────────────────────────────────────────────────

def discover_ollama_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST.rstrip('/')}/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        PROVIDERS["ollama"]["models"] = sorted(models)
        return models
    except Exception:
        return []


def discover_ollama_running():
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_HOST.rstrip('/')}/api/tags", timeout=3)
        return resp.status == 200
    except Exception:
        return False


# ── Agentic loop (the core — like Codex) ──────────────────────────────────

class AgenticLoop:
    """
    Implements the Codex-style agentic loop:
    1. Send messages + tools to LLM
    2. If LLM returns tool_calls → execute them → feed results back → repeat
    3. If LLM returns text only → done
    4. Max iterations to prevent infinite loops
    """

    def __init__(self, handler, provider, model):
        self.handler = handler
        self.provider = provider
        self.model = model
        self.messages = []
        self.iteration = 0

    def run(self, user_messages):
        sys_ctx = get_system_context()
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}
        ] + list(user_messages)

        while self.iteration < MAX_ITERS:
            self.iteration += 1
            self.handler._sse("iteration", f"{self.iteration}")

            # Determine if we should use tools
            use_tools = PROVIDERS.get(self.provider, {}).get("supports_tools", False)

            try:
                resp = call_llm_stream(
                    self.provider, self.messages, self.model,
                    tools=[SHELL_TOOL] if use_tools else None
                )
            except Exception as e:
                self.handler._sse("error", f"LLM call failed: {str(e)}")
                return

            # Parse the streaming response
            full_content = ""
            tool_calls_raw = {}
            finish_reason = None

            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream
            for chunk in iter_fn(resp):
                delta = chunk.get("delta", {})
                finish_reason = chunk.get("finish_reason") or finish_reason

                # Stream text content
                content = delta.get("content", "")
                if content:
                    full_content += content
                    self.handler._sse("token", content)

                # Collect tool calls
                tc_list = delta.get("tool_calls", [])
                for tc in tc_list:
                    if isinstance(tc, dict):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_raw:
                            tool_calls_raw[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        entry = tool_calls_raw[idx]
                        if tc.get("id"):
                            entry["id"] = tc["id"]
                        func = tc.get("function", {})
                        if func.get("name"):
                            entry["function"]["name"] = func["name"]
                        if func.get("arguments"):
                            entry["function"]["arguments"] += func["arguments"]

            # Build the assistant message
            assistant_msg = {"role": "assistant", "content": full_content or None}
            if tool_calls_raw:
                assistant_msg["tool_calls"] = [
                    tool_calls_raw[k] for k in sorted(tool_calls_raw.keys())
                ]
            self.messages.append(assistant_msg)

            # No tool calls → we're done
            if not tool_calls_raw:
                self.handler._sse("done", full_content)
                return

            # Execute each tool call
            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {"command": tc["function"]["arguments"]}

                command = args.get("command", "")
                work_dir = args.get("working_directory", "")

                self.handler._sse("tool_call", {
                    "id": tc.get("id", ""),
                    "name": func_name,
                    "command": command,
                })

                # Execute
                result = execute_command(command, work_dir or None)

                # Build tool result message
                result_text = ""
                if result.get("timed_out"):
                    result_text = f"Command timed out after {CMD_TIMEOUT}s"
                else:
                    if result["stdout"]:
                        result_text += result["stdout"]
                    if result["stderr"]:
                        result_text += ("\n" if result_text else "") + f"[stderr] {result['stderr']}"
                    result_text += f"\n[exit code: {result['exit_code']}]"
                    if not result_text.strip():
                        result_text = "[no output]"

                self.handler._sse("tool_result", {
                    "id": tc.get("id", ""),
                    "command": command,
                    "output": result_text,
                    "success": result["success"],
                    "exit_code": result["exit_code"],
                })

                # Add tool result to messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_text,
                })

        # Hit max iterations
        self.handler._sse("done", f"\n\n[Reached maximum iterations ({MAX_ITERS})]")

    # For providers that don't support tools, fall back to code block parsing
    def run_fallback(self, user_messages):
        sys_ctx = get_system_context()
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}
        ] + list(user_messages)

        while self.iteration < MAX_ITERS:
            self.iteration += 1
            self.handler._sse("iteration", f"{self.iteration}")

            try:
                resp = call_llm_stream(self.provider, self.messages, self.model)
            except Exception as e:
                self.handler._sse("error", f"LLM call failed: {str(e)}")
                return

            full_content = ""
            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream
            for chunk in iter_fn(resp):
                content = chunk.get("delta", {}).get("content", "")
                if content:
                    full_content += content
                    self.handler._sse("token", content)

            self.messages.append({"role": "assistant", "content": full_content})

            # Parse code blocks
            commands = parse_code_blocks(full_content)
            if not commands:
                self.handler._sse("done", full_content)
                return

            # Execute all commands
            results_text = ""
            for cmd in commands:
                self.handler._sse("tool_call", {
                    "id": f"fb-{self.iteration}",
                    "name": "execute_shell_command",
                    "command": cmd,
                })

                result = execute_command(cmd)
                output = ""
                if result["stdout"]:
                    output += result["stdout"]
                if result["stderr"]:
                    output += ("\n" if output else "") + f"[stderr] {result['stderr']}"
                output += f"\n[exit code: {result['exit_code']}]"

                self.handler._sse("tool_result", {
                    "id": f"fb-{self.iteration}",
                    "command": cmd,
                    "output": output.strip() or "[no output]",
                    "success": result["success"],
                    "exit_code": result["exit_code"],
                })

                results_text += f"$ {cmd}\n{output}\n\n"

            # Feed results back
            self.messages.append({
                "role": "user",
                "content": f"Command results:\n{results_text}\nContinue with the task. If commands failed, fix and retry. If done, summarize."
            })

        self.handler._sse("done", f"\n\n[Reached maximum iterations ({MAX_ITERS})]")


def parse_code_blocks(text):
    """Extract commands from ```bash blocks (fallback for non-tool providers)."""
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
                "version": "3.0",
                "providers": {
                    k: {"name": v["name"], "key_set": bool(get_api_key(k)),
                        "supports_tools": v.get("supports_tools", False)}
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
                    "supports_tools": v.get("supports_tools", False),
                }
            self.send_json(result)
        elif path == "/api/ollama/models":
            self.send_json({"models": discover_ollama_models(), "host": OLLAMA_HOST})
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
        result = execute_command(cmd, body.get("cwd"))
        self.send_json(result)

    def _handle_chat(self):
        body = self._read_body()
        messages  = body.get("messages", [])
        provider  = body.get("provider", DEFAULT_PROVIDER)
        model     = body.get("model", "")

        if provider not in PROVIDERS:
            self.send_json({"error": f"unknown provider: {provider}"}, 400)
            return

        key = get_api_key(provider)
        if PROVIDERS[provider]["needs_key"] and not key:
            self.send_json({"error": f"Set {PROVIDERS[provider]['env_key']}"}, 400)
            return

        # Set up SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            loop = AgenticLoop(self, provider, model)
            supports_tools = PROVIDERS.get(provider, {}).get("supports_tools", False)

            if supports_tools:
                loop.run(messages)
            else:
                loop.run_fallback(messages)

        except Exception as e:
            self._sse("error", f"Fatal: {str(e)}\n{traceback.format_exc()}")
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
    if discover_ollama_running():
        discover_ollama_models()
        ollama_count = len(PROVIDERS["ollama"]["models"])
        ollama_info = f"✓ {ollama_count} model(s)"
    else:
        ollama_info = "✗ not running"

    print(f"""
╔═══════════════════════════════════════════════════════╗
║             ShellAgent v3.0                           ║
║    Agentic AI Shell Agent — Tool Calling             ║
╠═══════════════════════════════════════════════════════╣
║  Dashboard  : http://localhost:{PORT:<24}║
║  Platform   : {sys.platform:<39}║
║  Cmd Timeout: {CMD_TIMEOUT}s (no limit by default){" "*(26-len(str(CMD_TIMEOUT)))}║
║  Max Iters  : {MAX_ITERS:<39}║
╠═══════════════════════════════════════════════════════╣
║  Providers                                            ║
║  ├─ OpenAI   : {"✓ key set" if OPENAI_API_KEY else "✗ no key":<39}║
║  ├─ NVIDIA   : {"✓ key set" if NVIDIA_API_KEY else "✗ no key":<39}║
║  └─ Ollama   : {ollama_info:<39}║
╚═══════════════════════════════════════════════════════╝
""")
    if not any([OPENAI_API_KEY, NVIDIA_API_KEY]):
        print("⚠  Set at least one API key:")
        print("   export OPENAI_API_KEY='sk-...'")
        print("   export NVIDIA_API_KEY='nvapi-...'")
        print("   Ollama works without a key if running locally\n")

    signal.signal(signal.SIGINT, lambda s, f: (print("\nShutting down..."), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    server = http.server.HTTPServer((HOST, PORT), AgentHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
