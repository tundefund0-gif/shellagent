#!/usr/bin/env python3
"""
ShellAgent - Lightweight AI-powered shell command agent with web dashboard.
Zero external dependencies beyond Python 3.8+ stdlib + requests (for API calls).
Supports 32-bit and 64-bit systems.
"""

import http.server
import json
import os
import sys
import subprocess
import threading
import time
import urllib.request
import urllib.error
import uuid
import signal
import io

PORT = int(os.environ.get("SHELLAGENT_PORT", 8765))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("SHELLAGENT_MODEL", "gpt-4o")
SHELL_TIMEOUT = int(os.environ.get("SHELLAGENT_TIMEOUT", "30"))
HOST = os.environ.get("SHELLAGENT_HOST", "0.0.0.0")
CWD = os.environ.get("SHELLAGENT_CWD", os.getcwd())

SYSTEM_PROMPT = """You are ShellAgent, an AI assistant that runs shell commands on the user's machine.
You can execute any shell command. Always:
1. Explain what you're about to do
2. Show the exact command
3. Explain the output clearly
When you want to run a command, output it wrapped in ```bash\n...\n``` blocks.
Always be helpful, concise, and accurate about what commands do.
If a command could be destructive, warn the user first.
Operating system info will be provided as context."""


def get_system_context():
    ctx = f"Working directory: {CWD}\n"
    try:
        ctx += f"OS: {sys.platform}\n"
        ctx += f"Python: {sys.version}\n"
        r = subprocess.run(["uname", "-a"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            ctx += f"System: {r.stdout.strip()}\n"
    except Exception:
        pass
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    ctx += f"Disk: {parts[2]} used / {parts[1]} total ({parts[4]} used)\n"
    except Exception:
        pass
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 3:
                    ctx += f"Memory: {parts[2]} used / {parts[1]} total\n"
    except Exception:
        pass
    return ctx


def call_openai_stream(messages):
    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": OPENAI_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    resp = urllib.request.urlopen(req, timeout=120)
    return resp


def parse_commands(text):
    """Extract bash commands from ```bash blocks."""
    commands = []
    lines = text.split("\n")
    in_block = False
    current_cmd = []
    for line in lines:
        if line.strip().startswith("```bash"):
            in_block = True
            current_cmd = []
            continue
        if line.strip() == "```" and in_block:
            if current_cmd:
                commands.append("\n".join(current_cmd))
            in_block = False
            current_cmd = []
            continue
        if in_block:
            current_cmd.append(line)
    return commands


def execute_command(cmd, cwd=None, timeout=None):
    timeout = timeout or SHELL_TIMEOUT
    cwd = cwd or CWD
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, env={**os.environ, "TERM": "dumb"}
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}" if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output or "[no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout: command exceeded {timeout}s]"
    except Exception as e:
        return f"[error: {str(e)}]"


class AgentHandler(http.server.BaseHTTPRequestHandler):
    sessions = {}

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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_file("templates/index.html", "text/html")
        elif self.path.startswith("/static/"):
            path = self.path[1:]
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            ct = {"css": "text/css", "js": "text/javascript", "png": "image/png", "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            self.serve_file(path, ct)
        elif self.path == "/api/health":
            self.send_json({"status": "ok", "model": OPENAI_MODEL, "platform": sys.platform})
        elif self.path == "/api/system":
            self.send_json({"context": get_system_context()})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/chat":
            self.handle_chat_stream()
        elif self.path == "/api/execute":
            self.handle_execute()
        else:
            self.send_error(404)

    def serve_file(self, filepath, content_type):
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

    def handle_execute(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        cmd = body.get("command", "")
        if not cmd:
            self.send_json({"error": "no command"}, 400)
            return
        output = execute_command(cmd)
        self.send_json({"output": output})

    def handle_chat_stream(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        messages = body.get("messages", [])
        auto_execute = body.get("auto_execute", True)

        if not OPENAI_API_KEY:
            self.send_json({"error": "OPENAI_API_KEY not set"}, 400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        sys_ctx = get_system_context()
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n--- System Context ---\n" + sys_ctx}] + messages

        full_text = ""
        try:
            resp = call_openai_stream(full_messages)
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
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
                        full_text += content
                        self.send_event("token", content)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            self.send_event("done", full_text)

            if auto_execute and full_text:
                cmds = parse_commands(full_text)
                for cmd in cmds:
                    self.send_event("executing", cmd)
                    output = execute_command(cmd)
                    self.send_event("output", output)

        except urllib.error.URLError as e:
            self.send_event("error", f"API error: {str(e)}")
        except Exception as e:
            self.send_event("error", str(e))
        finally:
            try:
                self.wfile.write(b"")
                self.wfile.flush()
            except Exception:
                pass

    def send_event(self, event, data):
        payload = json.dumps({"type": event, "data": data})
        msg = f"event: {event}\ndata: {payload}\n\n"
        try:
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass


def main():
    port = PORT
    server = http.server.HTTPServer((HOST, port), AgentHandler)
    print(f"""
╔══════════════════════════════════════════════╗
║           ShellAgent v1.0                    ║
║   AI-Powered Shell Command Agent            ║
╠══════════════════════════════════════════════╣
║  Dashboard: http://localhost:{port:<5}           ║
║  Model:     {OPENAI_MODEL:<31} ║
║  Platform:  {sys.platform:<31} ║
╚══════════════════════════════════════════════╝
""")
    if not OPENAI_API_KEY:
        print("⚠  Set OPENAI_API_KEY environment variable to use AI features")
        print("   Example: export OPENAI_API_KEY='sk-...'\n")

    def shutdown_handler(sig, frame):
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    server.serve_forever()


if __name__ == "__main__":
    main()
