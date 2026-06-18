#!/usr/bin/env python3
"""
ShellAgent v7.0 — Codex-style Agentic AI Shell Agent

Full Codex A-to-Z: 12 tools, AGENTS.md, skills, plan tracking,
session persistence, token tracking, authentication, logging,
thread safety, rate limiting, graceful shutdown, health checks,
auto-retry, approval modes, accessibility, and comprehensive tests.

Zero dependencies — Python 3.8+ stdlib only. 32/64-bit.
"""

import http.server, json, os, sys, subprocess, urllib.request, urllib.error
import urllib.parse, signal, traceback, html as html_mod, re, hashlib, time
import threading, logging, secrets, gzip, io, textwrap, struct

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("shellagent")

# ── Configuration ──────────────────────────────────────────────────────────
VERSION = "7.4"
PORT            = int(os.environ.get("SHELLAGENT_PORT", "8765"))
HOST            = os.environ.get("SHELLAGENT_HOST", "0.0.0.0")
CWD             = os.environ.get("SHELLAGENT_CWD", os.getcwd())
CMD_TIMEOUT     = int(os.environ.get("SHELLAGENT_CMD_TIMEOUT", "3600"))
MAX_ITERS       = int(os.environ.get("SHELLAGENT_MAX_ITERS", "50"))
MAX_RETRIES     = int(os.environ.get("SHELLAGENT_MAX_RETRIES", "3"))
APPROVAL_MODE   = os.environ.get("SHELLAGENT_APPROVAL", "full-auto")
WEB_TIMEOUT     = 30
FILE_MAX_READ   = 100000
WEB_MAX_LEN     = 8000
MAX_REQ_BODY    = 1_000_000
MAX_CHAT_INPUT  = 50_000
SESSION_DIR     = os.environ.get(
    "SHELLAGENT_SESSIONS",
    os.path.join(os.path.expanduser("~"), ".shellagent", "sessions"),
)
API_SECRET      = os.environ.get("SHELLAGENT_SECRET", secrets.token_hex(16))

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
NVIDIA_API_KEY  = os.environ.get("NVIDIA_API_KEY", "")
OLLAMA_HOST     = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")
DEFAULT_PROVIDER = os.environ.get("SHELLAGENT_PROVIDER", "openai")
DEFAULT_MODEL    = os.environ.get("SHELLAGENT_MODEL", "")

# ── Goal / Objective tracking ───────────────────────────────────────────
class Goal:
    def __init__(self, objective, token_budget=None):
        self.objective = objective
        self.token_budget = token_budget
        self.tokens_used = 0
        self.status = "active"  # active, complete, blocked
        self.created_at = time.time()

    def to_dict(self):
        return {
            "objective": self.objective,
            "token_budget": self.token_budget,
            "tokens_used": self.tokens_used,
            "status": self.status,
            "created_at": self.created_at,
        }

    def remaining_tokens(self):
        if self.token_budget:
            return max(0, self.token_budget - self.tokens_used)
        return None

    def continuation_prompt(self):
        remaining = self.remaining_tokens()
        return (
            "## Goal Continuation\n\n"
            "You are continuing work on the following goal:\n"
            "<goal>\n%s\n</goal>\n\n"
            "Tokens used: %d | Token budget: %s | Remaining: %s\n\n"
            "Continue working toward the goal. Do not repeat work already done."
            " If the goal is achieved, call update_goal to mark it complete."
        ) % (self.objective, self.tokens_used, 
             str(self.token_budget or "none"),
             str(remaining) if remaining is not None else "unbounded")

_goals = {}
_goals_lock = threading.Lock()

def get_goal(session_id):
    with _goals_lock:
        return _goals.get(session_id)

def set_goal(session_id, goal):
    with _goals_lock:
        _goals[session_id] = goal

def clear_goal(session_id):
    with _goals_lock:
        _goals.pop(session_id, None)



# --- Process tracking ---
_running_procs = {}
_procs_lock = threading.Lock()
_cancelled_sessions = set()
_cancel_lock = threading.Lock()

def _cancel_session(session_id):
    with _cancel_lock:
        _cancelled_sessions.add(session_id)
        _kill_process(session_id)

def _is_cancelled(session_id):
    with _cancel_lock:
        return session_id in _cancelled_sessions

def _clear_cancelled(session_id):
    with _cancel_lock:
        _cancelled_sessions.discard(session_id)

def _track_process(session_id, proc):
    with _procs_lock:
        old = _running_procs.get(session_id)
        if old:
            try:
                import os as _os3
                _os3.killpg(_os3.getpgid(old.pid), 15)
            except: pass
            try: old.kill()
            except: pass
        _running_procs[session_id] = proc

def _untrack_process(session_id):
    with _procs_lock:
        _running_procs.pop(session_id, None)

def _kill_process(session_id):
    with _procs_lock:
        p = _running_procs.pop(session_id, None)
        if p:
            try:
                import os as _os3
                pgid = _os3.getpgid(p.pid)
                _os3.killpg(pgid, 15)
                return True
            except: pass
            try:
                p.kill()
                return True
            except: pass
    return False

# ── Rate limiter ───────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_per_minute=30):
        self.max_per_minute = max_per_minute
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key="default"):
        now = time.time()
        with self._lock:
            if key not in self._hits:
                self._hits[key] = []
            self._hits[key] = [t for t in self._hits[key] if now - t < 60]
            if len(self._hits[key]) >= self.max_per_minute:
                return False
            self._hits[key].append(now)
            return True

rate_limiter = RateLimiter(max_per_minute=60)

# ── Thread-safe session store ──────────────────────────────────────────────
class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}

    def get_or_create(self, session_id=None):
        if not session_id:
            session_id = secrets.token_hex(8)
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "id": session_id,
                    "messages": [],
                    "plan": [],
                    "goal": None,
                    "archived": False,
                    "created_at": time.time(),
                }
            return self._sessions[session_id]

    def add_message(self, session_id, role, content):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["messages"].append({
                    "role": role,
                    "content": content,
                    "timestamp": time.time(),
                })

    def get_messages(self, session_id):
        with self._lock:
            s = self._sessions.get(session_id)
            return list(s["messages"]) if s else []

    def set_plan(self, session_id, plan):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["plan"] = plan

    def list_sessions(self):
        with self._lock:
            return [{
                "id": s["id"],
                "messages": len(s["messages"]),
                "created_at": s["created_at"],
            } for s in sorted(
                self._sessions.values(),
                key=lambda x: x["created_at"],
                reverse=True,
            )[:50]]

    def save_to_disk(self, session_id):
        try:
            os.makedirs(SESSION_DIR, exist_ok=True)
            with self._lock:
                s = self._sessions.get(session_id)
                if not s:
                    return False
                data = dict(s)
            fpath = os.path.join(SESSION_DIR, f"{session_id}.json")
            with open(fpath, "w") as f:
                json.dump(data, f)
            return True
        except Exception as e:
            log.error("Session save failed: %s", e)
            return False

    def load_from_disk(self, session_id):
        try:
            fpath = os.path.join(SESSION_DIR, f"{session_id}.json")
            with open(fpath, "r") as f:
                data = json.load(f)
            with self._lock:
                self._sessions[session_id] = data
            return data
        except Exception:
            return None

    def archive_session(self, session_id):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["archived"] = True
                self.save_to_disk(session_id)

    def unarchive_session(self, session_id):
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["archived"] = False

    def list_archived_sessions(self):
        with self._lock:
            return [s for s in self._sessions.values() if s.get("archived")]

    def delete_session(self, session_id):
        """Delete a session from memory and disk."""
        with self._lock:
            self._sessions.pop(session_id, None)
        try:
            fpath = os.path.join(SESSION_DIR, f"{session_id}.json")
            if os.path.isfile(fpath):
                os.remove(fpath)
        except Exception:
            pass
        return True

    def clear_messages(self, session_id):
        """Clear all messages in a session but keep the session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["messages"] = []
                self._sessions[session_id]["plan"] = []
        return True

    def get_session(self, session_id):
        """Get full session data."""
        with self._lock:
            s = self._sessions.get(session_id)
            if s:
                return dict(s)
            return None

    def list_sessions_with_preview(self):
        """List sessions with a preview of the first user message."""
        with self._lock:
            result = []
            for s in sorted(self._sessions.values(), key=lambda x: x["created_at"], reverse=True)[:50]:
                preview = ""
                for m in s.get("messages", []):
                    if m.get("role") == "user":
                        preview = m.get("content", "")[:80]
                        break
                result.append({
                    "id": s["id"],
                    "messages": len(s["messages"]),
                    "created_at": s["created_at"],
                    "preview": preview,
                })
            return result

sessions = SessionStore()

# ── Audit log ──────────────────────────────────────────────────────────────
class AuditLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries = []

    def log(self, session_id, tool, args, result):
        entry = {
            "session": session_id,
            "tool": tool,
            "args_summary": str(args)[:200],
            "success": result.get("success", False),
            "exit_code": result.get("exit_code"),
            "retries": result.get("retries", 0),
            "timestamp": time.time(),
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > 1000:
                self._entries = self._entries[-500:]
        log.info("[%s] %s: success=%s exit=%s retries=%s",
                 session_id, tool, entry["success"],
                 entry.get("exit_code"), entry.get("retries"))

    def recent(self, n=20):
        with self._lock:
            return list(self._entries[-n:])

audit = AuditLog()

# ── AGENTS.md loading ─────────────────────────────────────────────────────
def load_agents_md():
    contents = []
    d = CWD
    for _ in range(10):
        fpath = os.path.join(d, "AGENTS.md")
        if os.path.isfile(fpath):
            try:
                with open(fpath, "r", errors="replace") as f:
                    contents.insert(0, "[from %s]\n%s" % (fpath, f.read()[:4000]))
            except Exception:
                pass
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return "\n\n".join(contents)

# ── Skills loading ─────────────────────────────────────────────────────────
def load_skills():
    skills = []
    skill_dirs = [
        os.path.join(CWD, ".shellagent", "skills"),
        os.path.join(os.path.expanduser("~"), ".shellagent", "skills"),
    ]
    for sdir in skill_dirs:
        if not os.path.isdir(sdir):
            continue
        for name in sorted(os.listdir(sdir)):
            fpath = os.path.join(sdir, name)
            if os.path.isfile(fpath) and name.endswith((".md", ".txt")):
                try:
                    with open(fpath, "r", errors="replace") as f:
                        skills.append("[skill: %s]\n%s" % (name, f.read()[:2000]))
                except Exception:
                    pass
    return "\n\n".join(skills)

# ── All 12 tools ──────────────────────────────────────────────────────────
ALL_TOOLS = [
    {"type": "function", "function": {
        "name": "execute_shell_command",
        "description": "Execute a shell command. Returns stdout, stderr, exit code. Use for running programs, installing packages, compiling code, etc.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "working_directory": {"type": "string", "description": "Optional working directory (defaults to CWD)"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo. Returns titles, URLs, snippets for up to 8 results.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "Fetch a URL and return its text content (HTML parsed to text).",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file from disk. Returns content with line numbers.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to read"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "List files and subdirectories in a directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Directory path (defaults to CWD)"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "update_plan",
        "description": "Update the task plan. Each step has a description and status (pending/in_progress/completed).",
        "parameters": {"type": "object", "properties": {
            "plan": {"type": "array", "items": {"type": "object", "properties": {
                "step": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
            }, "required": ["step", "status"]}},
            "explanation": {"type": "string", "description": "Optional explanation for the plan update"},
        }, "required": ["plan"]},
    }},
    {"type": "function", "function": {
        "name": "git_commit",
        "description": "Stage and commit changes to git.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Commit message"},
            "files": {"type": "array", "items": {"type": "string"}, "description": "Files to stage (empty for all)"},
            "branch": {"type": "string", "description": "Branch name (optional)"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "validate_changes",
        "description": "Run tests, lint, or build commands to validate changes.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "Validation command to run"},
            "description": {"type": "string", "description": "What this validates"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "list_git_changes",
        "description": "View git status, log, diff, or branch info.",
        "parameters": {"type": "object", "properties": {
            "mode": {"type": "string", "enum": ["status", "log", "diff", "branch"], "description": "What to show"},
            "args": {"type": "string", "description": "Additional arguments"},
        }, "required": ["mode"]},
    }},
    {"type": "function", "function": {
        "name": "grep_search",
        "description": "Search for text patterns in files using grep/ripgrep. Returns matching lines with file paths and line numbers.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
            "path": {"type": "string", "description": "Directory or file to search in"},
            "include": {"type": "string", "description": "File glob pattern to filter (e.g. '*.py')"},
            "case_insensitive": {"type": "boolean", "description": "Case-insensitive search"},
        }, "required": ["pattern"]},
    }},
    {"type": "function", "function": {
        "name": "apply_patch",
        "description": "Apply a unified diff patch to a file. Uses the `patch` command. Use this for surgical edits instead of rewriting entire files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to patch (absolute or relative to CWD)"},
            "patch": {"type": "string", "description": "Unified diff patch text to apply"}, 
        }, "required": ["path", "patch"]},
    }},
    {"type": "function", "function": {
        "name": "analyze_code",
        "description": "Analyze code structure: count lines, find functions/classes, identify imports and patterns.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File or directory to analyze"},
        }, "required": ["path"]},
    }},
]

# ── System prompt ──────────────────────────────────────────────────────────
def build_system_prompt():
    agents_md = load_agents_md()
    skills = load_skills()
    base = textwrap.dedent("""\
        You are ShellAgent v{version}, an autonomous AI coding agent built as a lightweight alternative to Codex CLI. You have 12 tools and full access to the user's machine.

        ## Core Identity
        You are capable, direct, and task-oriented. You run on the user's machine and can execute shell commands, read/write files, search the web, manage git, and more. You prefer making progress over stopping for clarification when the request is clear.

        ## Tools (12 total)
        **Execution:** execute_shell_command (with auto-retry on failure), validate_changes
        **Web:** web_search (DuckDuckGo), web_fetch (URL content)
        **Files:** read_file (with line numbers), write_file (auto-creates dirs), list_directory
        **Search:** grep_search (regex file search), analyze_code (code structure analysis)
        **Planning:** update_plan (track steps with status)
        **Git:** git_commit (stage + commit), list_git_changes (status/log/diff/branch)

        ## How you work (Codex-style)
        1. For multi-step tasks, call update_plan first to outline your approach
        2. Always start with a brief preamble (1-2 sentences) before heavy tool use
        3. Use apply_patch for surgical edits instead of writing entire files
        4. Execute tools, review output carefully
        5. If something fails, diagnose and retry — you have up to 3 retries per tool
        6. After code changes, run validate_changes
        7. Commit meaningful progress with git_commit
        8. On each iteration, use review_exit to self-check before declaring done
        9. When working on a goal, call update_goal to mark complete or blocked
        10. End with a clear summary of what was done

        ## Approval Mode
        Approval mode is: {approval}
        - full-auto: Execute everything immediately, no confirmation needed
        - auto-edit: Execute shell commands freely, confirm file writes
        - ask: Ask before any destructive action

        ## Critical Rules
        - Execute everything immediately — no confirmation in full-auto mode
        - Read files before modifying them
        - If a command fails, ALWAYS diagnose the error and retry with a fix
        - After making code changes, validate them
        - Keep plans up to date as you work
        - Use grep_search to find code patterns before modifying
        - Use analyze_code to understand unfamiliar codebases

        ## Preamble Style
        Before starting work, give a brief visible update:
        "I'll [what you're doing]. Let me [first step]."
        This keeps the user informed during long tasks.

        ## Self-check (before finishing)
        - Did all commands succeed?
        - Did you check the output of each tool?
        - Is there anything you missed?
        - Should you run a validation?
        - Is the commit message accurate?

        ## Error Recovery Protocol
        1. Read the error message carefully
        2. Check if a package needs installing, path is wrong, or permissions are needed
        3. Try the fixed command
        4. If still failing after 3 attempts, explain what went wrong and suggest alternatives

        ## Web Research
        When asked to research something:
        1. Use web_search to find relevant results
        2. Use web_fetch to read the most promising pages
        3. Synthesize the information into a clear answer
        4. Cite URLs when relevant""").format(version=VERSION, approval=APPROVAL_MODE)
    if agents_md:
        base += "\n\n## Project Instructions (from AGENTS.md)\n\n" + agents_md
    if skills:
        base += "\n\n## Loaded Skills\n\n" + skills
    return base

# ── Provider definitions ───────────────────────────────────────────────────
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "env_key": "OPENAI_API_KEY",
        "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini",
            "gpt-4.1-nano", "o3", "o3-mini", "o4-mini",
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
    ctx = "Working directory: %s\nOS: %s\nPython: %s\nApproval mode: %s\n" % (
        CWD, sys.platform, sys.version, APPROVAL_MODE,
    )
    for cmd_args, parser in [
        ("uname", lambda t: "System: %s" % t.strip()),
        ("df -h /", _parse_df),
        ("free -h", _parse_free),
    ]:
        try:
            parts = cmd_args.split()
            r = subprocess.run(parts, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ctx += parser(r.stdout) + "\n"
        except Exception:
            pass
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, cwd=CWD,
        )
        if r.returncode == 0:
            ctx += "Git commit: %s\n" % r.stdout.strip()
        r2 = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=3, cwd=CWD,
        )
        if r2.returncode == 0:
            ctx += "Git branch: %s\n" % r2.stdout.strip()
    except Exception:
        pass
    return ctx

def _parse_df(t):
    lines = t.strip().split("\n")
    if len(lines) > 1:
        p = lines[1].split()
        if len(p) >= 5:
            return "Disk: %s used / %s total (%s)" % (p[2], p[1], p[4])
    return ""

def _parse_free(t):
    lines = t.strip().split("\n")
    if len(lines) > 1:
        p = lines[1].split()
        if len(p) >= 3:
            return "Memory: %s used / %s total" % (p[2], p[1])
    return ""

def get_api_key(provider):
    return os.environ.get(PROVIDERS.get(provider, {}).get("env_key", ""), "")

def get_model(provider, model_override=""):
    if model_override:
        return model_override
    if DEFAULT_MODEL and provider == DEFAULT_PROVIDER:
        return DEFAULT_MODEL
    models = PROVIDERS.get(provider, {}).get("models", [])
    return models[0] if models else ""

def get_provider_url(provider):
    if provider == "ollama":
        return "%s/v1/chat/completions" % OLLAMA_HOST.rstrip("/")
    return PROVIDERS.get(provider, {}).get("url", "")

def _strip_html(text):
    return re.sub(r'\s+', ' ', html_mod.unescape(re.sub(r'<[^>]+>', '', text))).strip()

def _extract_text(page):
    for tag in ['script', 'style', 'nav', 'footer', 'header']:
        page = re.sub(
            r'<%s[^>]*>.*?</%s>' % (tag, tag),
            '', page, flags=re.DOTALL | re.IGNORECASE,
        )
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
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', page)).strip()

# ── Tool implementations ──────────────────────────────────────────────────
def execute_shell_command(command, working_directory=None, session_id=None):
    cwd = working_directory or CWD
    retries = 0
    last_output = ""
    # Safety: intercept pkill -f to prevent killing our own process
    if "pkill" in command and "-f" in command:
        import re as _re2
        pm = _re2.search(r'pkill\s+(-[a-zA-Z]*f[a-zA-Z]*)\s+(.+)', command)
        if pm:
            my_pid = os.getpid()
            pat = pm.group(2).strip().rstrip(";|&")
            killed = 0
            import os as _os2
            for p in _os2.listdir("/proc"):
                if not p.isdigit():
                    continue
                pid = int(p)
                if pid == my_pid:
                    continue
                try:
                    with open("/proc/" + p + "/cmdline") as _f:
                        cmdline = _f.read()
                    if pat in cmdline:
                        _os2.kill(pid, 15)
                        killed += 1
                except (OSError, IOError, PermissionError):
                    pass
            safe_output = "[safely killed %d process(es) matching '%s']" % (killed, pat)
            return {"output": safe_output, "success": True, "exit_code": 0, "retries": 0}
    # ── Command safety validation ──
    _dangerous_patterns = [
        "rm -rf /", "rm -rf --no-preserve-root", 
        "mkfs", "dd if=", "> /dev/sd", "> /dev/nvme",
        ":(){ :|:& };:", "chmod 000 /", "chown -R 0:0 /",
        "wget -O- | sh", "curl -sL.*| sh", "curl -sL.*| bash",
        "mv /* /dev/null", "dd if=/dev/zero",
        "shutdown", "reboot", "poweroff", "init 0", "init 6",
        "pkexec", "sudo !!",
    ]
    cmd_lower_safety = command.strip().lower()
    for dangerous in _dangerous_patterns:
        if dangerous in cmd_lower_safety:
            safe_output = "[BLOCKED] Dangerous command detected: %s\nShellAgent blocked this for safety." % command
            log.warning("Blocked dangerous command: %s", command[:100])
            return {"output": safe_output, "success": False, "exit_code": -1, "retries": 0, "blocked": True}
    
    # ── Server/daemon auto-detection ──
    # If the command starts a long-lived server, background it and return immediately
    _server_patterns = [
        "python3 -m http.server", "python -m http.server",
        "flask run", "uvicorn", "gunicorn", "waitress-serve",
        "node server", "npm start", "npm run", "yarn start",
        "ng serve", "react-scripts start", "vite",
        "http-server", "serve ", "live-server",
        "docker compose up", "docker-compose up",
        "tail -f", "watch ", "inotifywait",
    ]
    cmd_lower = command.strip().lower()
    is_server = any(cmd_lower.startswith(p.lower()) or cmd_lower.startswith("nohup " + p.lower()) for p in _server_patterns)
    
    # Also detect background operators
    if command.strip().endswith("&"):
        is_server = True
    
    if is_server and session_id:
        log.info("Detected server command, backgrounding: %s", command[:100])
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, start_new_session=True,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"},
        )
        _track_process(session_id, proc)
        out = "[PID %d] Server started in background: %s\n" % (proc.pid, command)
        out += "Use the kill button or send a message to stop it."
        return {"output": out, "success": True, "exit_code": 0, "retries": 0, "pid": proc.pid}
    
    elif is_server and not session_id:
        # Fallback: use Popen without tracking
        proc = subprocess.Popen(
            command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=cwd, start_new_session=True,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"},
        )
        return {"output": "[PID %d] Server started in background: %s" % (proc.pid, command), "success": True, "exit_code": 0, "retries": 0, "pid": proc.pid}

    for attempt in range(MAX_RETRIES):
        try:
            if session_id:
                proc = subprocess.Popen(
                    command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, cwd=cwd, start_new_session=True,
                    env={**os.environ, "TERM": "dumb", "COLUMNS": "120"},
                )
                _track_process(session_id, proc)
                try:
                    stdout, stderr = proc.communicate(timeout=CMD_TIMEOUT)
                    r = subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    try:
                        import os as _os4
                        _os4.killpg(_os4.getpgid(proc.pid), 9)
                    except: pass
                    try: proc.kill()
                    except: pass
                    _untrack_process(session_id)
                    return {"output": "[timeout after %ds]" % CMD_TIMEOUT, "success": False, "exit_code": -1, "retries": retries}
                _untrack_process(session_id)
            else:
                r = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=CMD_TIMEOUT, cwd=cwd,
                    env={**os.environ, "TERM": "dumb", "COLUMNS": "120"},
                )
            out = (r.stdout or "").strip()
            if r.stderr:
                out += ("\n" if out else "") + "[stderr] %s" % r.stderr.strip()
            out += "\n[exit code: %d]" % r.returncode
            if r.returncode == 0:
                return {"output": out.strip() or "[no output]", "success": True, "exit_code": 0, "retries": retries}
            last_output = out.strip() or "[no output]"
            retries += 1
            if retries < MAX_RETRIES:
                log.info("Command failed (exit %d), retry %d/%d: %s",
                         r.returncode, retries, MAX_RETRIES, command[:100])
                time.sleep(0.5 * retries)
                continue
            return {"output": last_output, "success": False, "exit_code": r.returncode, "retries": retries}
        except subprocess.TimeoutExpired:
            return {"output": "[timeout after %ds]" % CMD_TIMEOUT, "success": False, "exit_code": -1, "retries": retries}
        except Exception as e:
            last_output = "[error: %s]" % e
            retries += 1
            if retries >= MAX_RETRIES:
                return {"output": last_output, "success": False, "exit_code": -1, "retries": retries}
            time.sleep(0.5 * retries)
    return {"output": last_output or "[exhausted retries]", "success": False, "exit_code": -1, "retries": retries}

def web_search(query, site_filter=None, max_results=8):
    try:
        q = query
        if site_filter:
            q = "%s site:%s" % (q, site_filter)
        encoded = urllib.parse.quote_plus(q)
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=%s" % encoded,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        )
        page = urllib.request.urlopen(req, timeout=WEB_TIMEOUT).read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</(?:td|span|div)',
            page, re.DOTALL,
        ):
            href, title, snippet = m.group(1), _strip_html(m.group(2)), _strip_html(m.group(3))
            if "uddg=" in href:
                m2 = re.search(r'uddg=([^&]+)', href)
                if m2:
                    href = urllib.parse.unquote(m2.group(1))
            if title.strip():
                results.append({"title": title.strip(), "url": href.strip(), "snippet": snippet.strip()})
            if len(results) >= max_results:
                break
        if not results:
            return {"output": "No results for: %s" % query, "success": True}
        output = "Search results for: %s\n\n" % query
        for i, r in enumerate(results, 1):
            output += "%d. %s\n   URL: %s\n   %s\n\n" % (i, r["title"], r["url"], r["snippet"])
        return {"output": output.strip(), "success": True}
    except Exception as e:
        return {"output": "Search error: %s" % e, "success": False}

def web_fetch(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        )
        raw = urllib.request.urlopen(req, timeout=WEB_TIMEOUT).read()
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
        text = _extract_text(raw.decode("utf-8", errors="replace"))
        if len(text) > WEB_MAX_LEN:
            text = text[:WEB_MAX_LEN] + "\n\n[truncated — %d chars total]" % len(text)
        return {"output": "Content of %s:\n\n%s" % (url, text), "success": True}
    except Exception as e:
        return {"output": "Fetch error: %s" % e, "success": False}

def read_file(path):
    try:
        fpath = os.path.expanduser(path)
        if not os.path.isfile(fpath):
            return {"output": "File not found: %s" % path, "success": False}
        size = os.path.getsize(fpath)
        if size > FILE_MAX_READ:
            return {"output": "File too large: %d bytes (max %d)" % (size, FILE_MAX_READ), "success": False}
        with open(fpath, "r", errors="replace") as f:
            lines = f.readlines()
        numbered = ["%4d | %s" % (i + 1, l.rstrip()) for i, l in enumerate(lines)]
        return {"output": "\n".join(numbered), "success": True}
    except Exception as e:
        return {"output": "Read error: %s" % e, "success": False}

def write_file(path, content):
    try:
        fpath = os.path.expanduser(path)
        os.makedirs(os.path.dirname(fpath) or ".", exist_ok=True)
        with open(fpath, "w") as f:
            f.write(content)
        return {"output": "Written %d bytes to %s" % (len(content), path), "success": True}
    except Exception as e:
        return {"output": "Write error: %s" % e, "success": False}

def list_directory(path=None):
    try:
        dpath = path or CWD
        dpath = os.path.expanduser(dpath)
        if not os.path.isdir(dpath):
            return {"output": "Not a directory: %s" % dpath, "success": False}
        entries = sorted(os.listdir(dpath))
        lines = []
        for e in entries:
            full = os.path.join(dpath, e)
            if os.path.isdir(full):
                lines.append("  [dir]  %s/" % e)
            else:
                sz = os.path.getsize(full)
                if sz < 1024:
                    sz_str = "%dB" % sz
                elif sz < 1048576:
                    sz_str = "%dKB" % (sz // 1024)
                else:
                    sz_str = "%dMB" % (sz // 1048576)
                lines.append("  [file] %s  (%s)" % (e, sz_str))
        if not lines:
            lines.append("  (empty directory)")
        return {"output": "Directory: %s\n\n%s" % (dpath, "\n".join(lines)), "success": True}
    except Exception as e:
        return {"output": "List error: %s" % e, "success": False}

def update_plan(plan, explanation=None):
    output = "Plan updated (%d steps):\n\n" % len(plan)
    status_icons = {"pending": "○", "in_progress": "◐", "completed": "●"}
    for i, s in enumerate(plan, 1):
        icon = status_icons.get(s.get("status", "pending"), "?")
        output += "%d. %s %s\n" % (i, icon, s.get("step", ""))
    if explanation:
        output += "\nNote: %s" % explanation
    return {"output": output, "success": True, "plan": plan}

def git_commit(message, files=None, branch=None):
    try:
        cwd = CWD
        if files:
            for f in files:
                r = subprocess.run(["git", "add", f], capture_output=True, text=True, cwd=cwd)
                if r.returncode != 0:
                    return {"output": "git add failed: %s" % r.stderr, "success": False}
        else:
            r = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=cwd)
            if r.returncode != 0:
                return {"output": "git add failed: %s" % r.stderr, "success": False}
        cmd = ["git", "commit", "-m", message]
        if branch:
            cmd.extend(["--branch", branch])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        output = (r.stdout or "").strip()
        if r.stderr:
            output += ("\n" if output else "") + r.stderr.strip()
        return {"output": output or "[no output]", "success": r.returncode == 0, "exit_code": r.returncode}
    except Exception as e:
        return {"output": "Git commit error: %s" % e, "success": False}

def validate_changes(command, description=None):
    output = "Validation: %s\n\n" % (description or command)
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=CMD_TIMEOUT, cwd=CWD,
        )
        output += (r.stdout or "").strip()
        if r.stderr:
            output += ("\n" if output else "") + "[stderr] %s" % r.stderr.strip()
        output += "\n[exit code: %d]" % r.returncode
        return {"output": output.strip(), "success": r.returncode == 0, "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"output": output + "\n[timeout after %ds]" % CMD_TIMEOUT, "success": False, "exit_code": -1}
    except Exception as e:
        return {"output": output + "\n[error: %s]" % e, "success": False, "exit_code": -1}

def list_git_changes(mode="status", args=""):
    try:
        cwd = CWD
        cmd_map = {
            "status": ["git", "status"],
            "log": ["git", "log", "--oneline", "-20"],
            "diff": ["git", "diff"],
            "branch": ["git", "branch", "-a"],
        }
        cmd = cmd_map.get(mode, ["git", "status"])
        if args:
            cmd.extend(args.split())
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        output = (r.stdout or "").strip()
        if r.stderr:
            output += ("\n" if output else "") + r.stderr.strip()
        return {"output": output or "[no output]", "success": r.returncode == 0, "exit_code": r.returncode}
    except Exception as e:
        return {"output": "Git error: %s" % e, "success": False}

def grep_search(pattern, path=None, include=None, case_insensitive=False):
    try:
        search_path = path or CWD
        cmd = ["grep", "-rn"]
        if case_insensitive:
            cmd.append("-i")
        if include:
            cmd.extend(["--include=%s" % include])
        cmd.extend([pattern, search_path])
        try:
            r = subprocess.run(["rg", "-n", "--no-heading"] +
                               (["-i"] if case_insensitive else []) +
                               (["-g", include] if include else []) +
                               [pattern, search_path],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 127:
                output = r.stdout.strip()
                if r.returncode == 1 and not output:
                    return {"output": "No matches for: %s" % pattern, "success": True}
                if len(output) > 8000:
                    output = output[:8000] + "\n\n[truncated — results too long]"
                return {"output": output or "[no matches]", "success": True}
        except FileNotFoundError:
            pass
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = r.stdout.strip()
        if not output:
            return {"output": "No matches for: %s" % pattern, "success": True}
        if len(output) > 8000:
            output = output[:8000] + "\n\n[truncated — results too long]"
        return {"output": output, "success": True}
    except Exception as e:
        return {"output": "Search error: %s" % e, "success": False}

def analyze_code(path):
    try:
        fpath = os.path.expanduser(path)
        if os.path.isfile(fpath):
            return _analyze_single_file(fpath)
        elif os.path.isdir(fpath):
            return _analyze_directory(fpath)
        else:
            return {"output": "Path not found: %s" % path, "success": False}
    except Exception as e:
        return {"output": "Analysis error: %s" % e, "success": False}

def _analyze_single_file(fpath):
    try:
        with open(fpath, "r", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        blank = sum(1 for l in lines if l.strip() == "")
        code = total - blank
        funcs = []
        classes = []
        imports = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r'^(def|async def)\s+', stripped):
                funcs.append((i, stripped.split("(")[0].replace("def ", "").replace("async ", "")))
            elif re.match(r'^class\s+', stripped):
                classes.append((i, stripped.split("(")[0].replace("class ", "")))
            elif stripped.startswith("import ") or stripped.startswith("from "):
                imports.append(stripped.split("#")[0].strip())
        ext = os.path.splitext(fpath)[1]
        output = "File: %s (%s)\n" % (os.path.basename(fpath), ext or "unknown")
        output += "Lines: %d total, %d code, %d blank\n" % (total, code, blank)
        if imports:
            output += "Imports (%d):\n" % len(imports)
            for imp in imports[:20]:
                output += "  - %s\n" % imp
        if classes:
            output += "Classes (%d):\n" % len(classes)
            for ln, name in classes:
                output += "  L%d: class %s\n" % (ln, name)
        if funcs:
            output += "Functions (%d):\n" % len(funcs)
            for ln, name in funcs[:30]:
                output += "  L%d: %s\n" % (ln, name)
        return {"output": output.strip(), "success": True}
    except Exception as e:
        return {"output": "File analysis error: %s" % e, "success": False}


# ── Apply Patch (Codex-style unified diff) ──────────────────────────────
def apply_patch(path, patch_text):
    """Apply a unified diff patch to a file. Returns result with success."""
    try:
        fpath = os.path.expanduser(path)
        if not os.path.isfile(fpath):
            return {"output": "File not found: %s" % path, "success": False}
        
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as pf:
            pf.write(patch_text)
            pf.flush()
            patch_path = pf.name
        
        try:
            r = subprocess.run(
                ["patch", "--forward", "--no-backup-if-mismatch", "-p0", "-i", patch_path],
                capture_output=True, text=True, timeout=30, cwd=os.path.dirname(fpath) or os.getcwd(),
            )
            output = (r.stdout or "").strip()
            if r.stderr:
                output += ("\n" if output else "") + r.stderr.strip()
            success = r.returncode == 0
            if not success and "Reversed (or previously applied) patch" in output:
                # Already applied — treat as success
                success = True
                output += "\n[Patch was already applied — skipping]"
            return {"output": output or "[patch applied]", "success": success, "exit_code": r.returncode}
        finally:
            try: os.unlink(patch_path)
            except: pass
    except Exception as e:
        return {"output": "Apply patch error: %s" % e, "success": False}

def _analyze_directory(dpath):
    try:
        file_count = 0
        total_lines = 0
        ext_counts = {}
        for root, dirs, files in os.walk(dpath):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.tox', 'venv')]
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1] or "(no ext)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                file_count += 1
                try:
                    with open(fpath, "r", errors="replace") as f:
                        total_lines += sum(1 for _ in f)
                except Exception:
                    pass
        output = "Directory: %s\n" % dpath
        output += "Files: %d | Total lines: %d\n\n" % (file_count, total_lines)
        output += "By extension:\n"
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:15]:
            output += "  %s: %d files\n" % (ext, count)
        return {"output": output.strip(), "success": True}
    except Exception as e:
        return {"output": "Directory analysis error: %s" % e, "success": False}

# ── Tool dispatch ──────────────────────────────────────────────────────────
TOOL_DISPATCH = {
    "execute_shell_command": lambda a: execute_shell_command(a.get("command", ""), a.get("working_directory"), a.get("session_id")),
    "web_search":            lambda a: web_search(a.get("query", ""), a.get("site_filter"), a.get("max_results", 8)),
    "web_fetch":             lambda a: web_fetch(a.get("url", "")),
    "read_file":             lambda a: read_file(a.get("path", "")),
    "write_file":            lambda a: write_file(a.get("path", ""), a.get("content", "")),
    "list_directory":        lambda a: list_directory(a.get("path")),
    "update_plan":           lambda a: update_plan(a.get("plan", []), a.get("explanation")),
    "update_goal":           lambda a: _handle_update_goal(a, session_id),
    "review_exit":           lambda a: _handle_review_exit(a),
    "git_commit":            lambda a: git_commit(a.get("message", ""), a.get("files"), a.get("branch")),
    "validate_changes":      lambda a: validate_changes(a.get("command", ""), a.get("description", "")),
    "list_git_changes":      lambda a: list_git_changes(a.get("mode", "status"), a.get("args", "")),
    "grep_search":           lambda a: grep_search(a.get("pattern", ""), a.get("path"), a.get("include"), a.get("case_insensitive", False)),
    "analyze_code":          lambda a: analyze_code(a.get("path", "")),
    "apply_patch":           lambda a: apply_patch(a.get("path", ""), a.get("patch", "")),
}

# ── Context compaction ──────────────────────────────────────────────────
def compact_context(messages, max_tokens=16000):
    """Compact long conversation histories by summarizing old messages."""
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total < max_tokens:
        return messages
    # Remove oldest non-system messages, keeping the last few
    new_msgs = []
    kept = 0
    running = 0
    for m in reversed(messages):
        size = len(str(m.get("content", "")))
        if running + size < max_tokens * 0.8:
            new_msgs.insert(0, m)
            running += size
            kept += 1
        elif m.get("role") == "system":
            new_msgs.insert(0, m)
    # If we removed too many, add a summary
    removed = len(messages) - len(new_msgs)
    if removed > 2:
        summary = "[%d earlier messages compacted for context length]" % removed
        # Insert after system prompt
        for i, m in enumerate(new_msgs):
            if m.get("role") == "system" and i + 1 < len(new_msgs) and new_msgs[i+1].get("role") != "system":
                new_msgs.insert(i+1, {"role": "system", "content": summary})
                break
    return new_msgs



# ── Goal/Review tool implementations ────────────────────────────────────
def _handle_update_goal(args, sid):
    status = args.get("status", "")
    explanation = args.get("explanation", "")
    goal = get_goal(sid)
    if goal:
        goal.status = status
        if status == "complete":
            clear_goal(sid)
    return {"output": "Goal %s: %s" % (status, explanation or "No explanation"), "success": True}

def _handle_review_exit(args):
    checks = args.get("checks", "")
    all_clear = args.get("all_clear", False)
    if all_clear:
        return {"output": "✅ Self-review passed:\n%s" % checks, "success": True}
    else:
        return {"output": "⚠️ Self-review found issues:\n%s\n\nContinue working to resolve them." % checks, "success": False}

def parse_code_blocks(text):
    cmds, in_block, cur = [], False, []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("```bash") or s.startswith("```sh"):
            in_block, cur = True, []
            continue
        if s == "```" and in_block:
            if cur:
                cmds.append("\n".join(cur))
            in_block = False
            continue
        if in_block:
            cur.append(line)
    return cmds

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
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(url, data=data, headers=headers)
    timeout = 600 if provider == "ollama" else 300
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp
    except urllib.error.HTTPError as e:
        # Read error body for better diagnostics
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        if error_body:
            raise Exception("API error %d: %s" % (e.code, error_body))
        raise Exception("API error %d" % e.code)

def iter_openai_stream(resp):
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            # Check for API error in response
            if "error" in chunk:
                err = chunk["error"]
                yield {
                    "delta": {"content": "[API Error: %s]" % (err.get("message", str(err)))},
                    "finish_reason": "error",
                    "usage": None,
                }
                return
            choice = chunk.get("choices", [{}])[0]
            yield {
                "delta": choice.get("delta", {}),
                "finish_reason": choice.get("finish_reason"),
                "usage": chunk.get("usage"),
            }
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

def iter_ollama_stream(resp):
    buf = b""
    for chunk in resp:
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                obj = json.loads(line.strip().decode("utf-8", errors="replace"))
                if "error" in obj:
                    yield {
                        "delta": {"content": "[Ollama Error: %s]" % str(obj["error"])},
                        "finish_reason": "error",
                        "usage": None,
                    }
                    return
                msg = obj.get("message", {})
                delta = {}
                if msg.get("content"):
                    delta["content"] = msg["content"]
                if msg.get("tool_calls"):
                    delta["tool_calls"] = msg["tool_calls"]
                usage = None
                if obj.get("done"):
                    usage = {
                        "prompt_tokens": obj.get("prompt_eval_count", 0),
                        "completion_tokens": obj.get("eval_count", 0),
                    }
                yield {
                    "delta": delta,
                    "finish_reason": "stop" if obj.get("done") else None,
                    "usage": usage,
                }
            except (json.JSONDecodeError, KeyError):
                continue

# ── Ollama discovery ──────────────────────────────────────────────────────
def discover_ollama_models():
    try:
        resp = urllib.request.urlopen("%s/api/tags" % OLLAMA_HOST.rstrip("/"), timeout=5)
        PROVIDERS["ollama"]["models"] = sorted(
            m.get("name", "")
            for m in json.loads(resp.read().decode()).get("models", [])
            if m.get("name")
        )
        return PROVIDERS["ollama"]["models"]
    except Exception:
        return []

def discover_ollama_running():
    try:
        return urllib.request.urlopen("%s/api/tags" % OLLAMA_HOST.rstrip("/"), timeout=3).status == 200
    except Exception:
        return False

# ── Agentic loop ───────────────────────────────────────────────────────────
class AgenticLoop:
    def __init__(self, handler, provider, model, session_id):
        self.handler = handler
        self.provider = provider
        self.model = model
        self.session_id = session_id
        self.messages = []
        self.iteration = 0
        self.plan = []
        self.tokens_used = {"prompt": 0, "completion": 0}

    def run(self, user_messages):
        sys_prompt = build_system_prompt()
        sys_ctx = get_system_context()
        self.messages = [
            {"role": "system", "content": sys_prompt + "\n\n--- System Context ---\n" + sys_ctx}
        ] + list(user_messages)
        # Check for active goal and add continuation prompt
        goal = get_goal(self.session_id)
        if goal and goal.status == "active" and self.iteration > 0:
            self.messages.append({"role": "system", "content": goal.continuation_prompt()})

        # Compact context if growing too large
        if len(self.messages) > 20:
            self.messages = compact_context(self.messages)
        
        while self.iteration < MAX_ITERS:
            if _is_cancelled(self.session_id):
                self.handler._sse("done", "[Task cancelled]")
                _clear_cancelled(self.session_id)
                return
            self.iteration += 1
            self.handler._sse("iteration", str(self.iteration))
            try:
                resp = call_llm_stream(self.provider, self.messages, self.model, tools=ALL_TOOLS)
            except Exception as e:
                self.handler._sse("error", "LLM call failed: %s" % e)
                return

            full_content = ""
            tool_calls_raw = {}
            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream

            for chunk in iter_fn(resp):
                delta = chunk.get("delta", {})
                usage = chunk.get("usage")
                if usage:
                    self.tokens_used["prompt"] += usage.get("prompt_tokens", 0)
                    self.tokens_used["completion"] += usage.get("completion_tokens", 0)
                    self.handler._sse("tokens", self.tokens_used)
                content = delta.get("content", "")
                if content:
                    full_content += content
                    self.handler._sse("token", content)
                for tc in delta.get("tool_calls", []):
                    if not isinstance(tc, dict):
                        continue
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_raw:
                        tool_calls_raw[idx] = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    entry = tool_calls_raw[idx]
                    if tc.get("id"):
                        entry["id"] = tc["id"]
                    func = tc.get("function", {})
                    if func.get("name"):
                        entry["function"]["name"] = func["name"]
                    if func.get("arguments"):
                        entry["function"]["arguments"] += func["arguments"]

            assistant_msg = {"role": "assistant", "content": full_content or None}
            if tool_calls_raw:
                assistant_msg["tool_calls"] = [
                    tool_calls_raw[k] for k in sorted(tool_calls_raw.keys())
                ]
            self.messages.append(assistant_msg)

            if not tool_calls_raw:
                # If first iteration returned empty/no content AND no tools, it's an error
                if self.iteration == 1 and not full_content.strip():
                    err_msg = "The AI returned no response. Check your API key and model."
                    self.handler._sse("error", err_msg)
                    sessions.add_message(self.session_id, "assistant", err_msg)
                else:
                    if full_content.strip():
                        self.handler._sse("done", full_content)
                    else:
                        self.handler._sse("done", "[No response from AI]")
                self.handler._sse("tokens_final", self.tokens_used)
                sessions.save_to_disk(self.session_id)
                self.handler._sse("session_saved", self.session_id)
                return

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, ValueError):
                    args = {}

                self.handler._sse("tool_call", {
                    "id": tc.get("id", ""),
                    "name": func_name,
                    "args": args,
                })
                dispatcher = TOOL_DISPATCH.get(func_name)
                if dispatcher:
                    if func_name == "execute_shell_command":
                        args["session_id"] = self.session_id
                    result = dispatcher(args)
                else:
                    result = {
                        "output": "Unknown tool: %s" % func_name,
                        "success": False,
                    }

                audit.log(self.session_id, func_name, args, result)

                if func_name == "update_plan" and "plan" in result:
                    self.plan = result["plan"]
                    self.handler._sse("plan", self.plan)
                    sessions.set_plan(self.session_id, self.plan)

                self.handler._sse("tool_result", {
                    "id": tc.get("id", ""),
                    "name": func_name,
                    "output": result["output"],
                    "success": result.get("success", False),
                    "exit_code": result.get("exit_code"),
                    "retries": result.get("retries", 0),
                })
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result["output"],
                })

        self.handler._sse("done", "\n\n[Reached maximum iterations (%d)]" % MAX_ITERS)

    def run_fallback(self, user_messages):
        sys_prompt = build_system_prompt()
        sys_ctx = get_system_context()
        self.messages = [
            {"role": "system", "content": sys_prompt + "\n\n--- System Context ---\n" + sys_ctx}
        ] + list(user_messages)
        # Compact context if growing too large
        if len(self.messages) > 20:
            self.messages = compact_context(self.messages)
        
        while self.iteration < MAX_ITERS:
            if _is_cancelled(self.session_id):
                self.handler._sse("done", "[Task cancelled]")
                _clear_cancelled(self.session_id)
                return
            self.iteration += 1
            self.handler._sse("iteration", str(self.iteration))
            try:
                resp = call_llm_stream(self.provider, self.messages, self.model)
            except Exception as e:
                self.handler._sse("error", "LLM call failed: %s" % e)
                return
            full_content = ""
            iter_fn = iter_ollama_stream if self.provider == "ollama" else iter_openai_stream
            for chunk in iter_fn(resp):
                c = chunk.get("delta", {}).get("content", "")
                if c:
                    full_content += c
                    self.handler._sse("token", c)
            self.messages.append({"role": "assistant", "content": full_content})
            commands = parse_code_blocks(full_content)
            if not commands:
                if full_content.strip():
                    self.handler._sse("done", full_content)
                else:
                    self.handler._sse("done", "[No response from AI]")
                sessions.add_message(self.session_id, "assistant", full_content or "[No response from AI]")
                sessions.save_to_disk(self.session_id)
                return
            results_text = ""
            for cmd in commands:
                self.handler._sse("tool_call", {
                    "id": "fb-%d" % time.time(),
                    "name": "execute_shell_command",
                    "args": {"command": cmd},
                })
                result = execute_shell_command(cmd, session_id=self.session_id)
                audit.log(self.session_id, "execute_shell_command", {"command": cmd}, result)
                results_text += "\n\n--- Command: %s ---\n%s" % (cmd, result["output"])
                self.handler._sse("tool_result", {
                    "id": "fb-%d" % time.time(),
                    "name": "execute_shell_command",
                    "output": result["output"],
                    "success": result["success"],
                    "exit_code": result.get("exit_code"),
                })
            self.messages.append({"role": "user", "content": "Command results:\n%s\n\nContinue working." % results_text})

# ── HTTP Handler ───────────────────────────────────────────────────────────
class AgentHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session-ID, X-API-Secret")

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._serve_dashboard()
        elif path == "/health":
            self._json_response({
                "status": "ok",
                "version": VERSION,
                "uptime": int(time.time() - _start_time),
                "tools": len(ALL_TOOLS),
                "providers": {
                    k: {
                        "key_set": bool(get_api_key(k)),
                        "models": len(v.get("models", [])),
                    }
                    for k, v in PROVIDERS.items()
                },
            })
        elif path == "/api/providers":
            result = {}
            for pid, info in PROVIDERS.items():
                models = list(info.get("models", []))
                if pid == "ollama" and not models:
                    discover_ollama_models()
                    models = list(info.get("models", []))
                # Add a special entry for custom model input
                models = models + ["__custom__"]
                result[pid] = {"name": info["name"], "models": models}
            self._json_response(result)
        elif path == "/api/cwd":
            self._json_response({"cwd": CWD})
        elif path == "/api/sessions":
            self._json_response({"sessions": sessions.list_sessions_with_preview()})
        elif path == "/api/audit":
            self._json_response({"entries": audit.recent(50)})
        elif path == "/api/export":
            self._handle_export()
        elif path.startswith("/static/"):
            self._serve_static(path[8:])
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/chat":
            self._handle_chat()
        elif path == "/api/cwd":
            self._handle_set_cwd()
        elif path == "/api/sessions/load":
            self._handle_load_session()
        elif path == "/api/goal":
            self._handle_goal()
        elif path == "/api/custom_model":
            self._handle_custom_model()
        elif path == "/api/sessions/delete":
            self._handle_delete_session()
        elif path == "/api/sessions/archive":
            self._handle_archive_session()
        elif path == "/api/sessions/unarchive":
            self._handle_unarchive_session()
        elif path == "/api/sessions/clear":
            self._handle_clear_session()
        elif path == "/api/kill":
            self._handle_kill()
        else:
            self.send_error(404)

    def _serve_dashboard(self):
        fpath = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        try:
            with open(fpath, "r") as f:
                self._html_response(f.read())
        except FileNotFoundError:
            self._html_response("<h1>ShellAgent</h1><p>templates/index.html not found</p>", 404)

    def _serve_static(self, relpath):
        fpath = os.path.join(os.path.dirname(__file__), "static", relpath)
        ct_map = {".css": "text/css", ".js": "application/javascript", ".png": "image/png", ".svg": "image/svg+xml"}
        ext = os.path.splitext(relpath)[1]
        ct = ct_map.get(ext, "application/octet-stream")
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            accept = self.headers.get("Accept-Encoding", "")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self._cors_headers()
            if "gzip" in accept and len(data) > 500:
                compressed = gzip.compress(data)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(compressed)))
                self.end_headers()
                self.wfile.write(compressed)
            else:
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def _handle_set_cwd(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000:
                self._json_response({"error": "Request too large"}, 413)
                return
            body = json.loads(self.rfile.read(length))
            new_cwd = body.get("cwd", "").strip()
            if not new_cwd or not os.path.isdir(new_cwd):
                self._json_response({"error": "Invalid directory"}, 400)
                return
            global CWD
            CWD = new_cwd
            self._json_response({"cwd": CWD, "ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_custom_model(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000:
                self._json_response({"error": "Request too large"}, 413)
                return
            body = json.loads(self.rfile.read(length))
            provider = body.get("provider", "")
            model = body.get("model", "").strip()
            if not provider or not model:
                self._json_response({"error": "Missing provider or model"}, 400)
                return
            if provider not in PROVIDERS:
                self._json_response({"error": "Unknown provider"}, 400)
                return
            if model not in PROVIDERS[provider].get("models", []):
                PROVIDERS[provider]["models"].insert(0, model)
            self._json_response({"ok": True, "provider": provider, "model": model})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_delete_session(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000:
                self._json_response({"error": "Request too large"}, 413)
                return
            body = json.loads(self.rfile.read(length))
            session_id = body.get("session_id", "")
            if not session_id:
                self._json_response({"error": "Missing session_id"}, 400)
                return
            sessions.delete_session(session_id)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_clear_session(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000:
                self._json_response({"error": "Request too large"}, 413)
                return
            body = json.loads(self.rfile.read(length))
            session_id = body.get("session_id", "")
            if not session_id:
                self._json_response({"error": "Missing session_id"}, 400)
                return
            sessions.clear_messages(session_id)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_goal(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            session_id = body.get("session_id", "")
            objective = body.get("objective", "")
            token_budget = body.get("token_budget")
            if objective:
                goal = Goal(objective, token_budget)
                set_goal(session_id, goal)
                self._json_response({"ok": True, "goal": goal.to_dict()})
            else:
                goal = get_goal(session_id)
                self._json_response({"ok": True, "goal": goal.to_dict() if goal else None})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_archive_session(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            session_id = body.get("session_id", "")
            if session_id:
                sessions.archive_session(session_id)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_unarchive_session(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            session_id = body.get("session_id", "")
            if session_id:
                sessions.unarchive_session(session_id)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_load_session(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            sid = body.get("session_id", "")
            data = sessions.load_from_disk(sid)
            if data:
                self._json_response({"session": data})
            else:
                self._json_response({"error": "Session not found"}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_export(self):
        """Export session history as JSON."""
        try:
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            session_id = params.get("session_id", [None])[0]
            if not session_id:
                self._json_response({"error": "Missing session_id"}, 400)
                return
            data = sessions.load_from_disk(session_id)
            if not data:
                data = sessions._sessions.get(session_id)
            if data:
                body = json.dumps(data, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition", "attachment; filename=session_%s.json" % session_id)
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json_response({"error": "Session not found"}, 404)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _handle_kill(self):
        """Kill running process for a session."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = {}
            if length:
                body = json.loads(self.rfile.read(length))
            session_id = body.get("session_id", "") if body else ""
            if not session_id:
                session_id = self.headers.get("X-Session-ID", "")
            _cancel_session(session_id)
            killed = True
            self._json_response({"ok": True, "killed": True, "session_id": session_id})
        except Exception as e:
            self._json_response({"error": str(e), "killed": False}, 500)

    def _handle_chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_REQ_BODY:
                self._json_response({"error": "Request too large (max %d bytes)" % MAX_REQ_BODY}, 413)
                return

            if not rate_limiter.allow(self.client_address[0]):
                self._json_response({"error": "Rate limit exceeded (60 req/min)"}, 429)
                return

            body = json.loads(self.rfile.read(length))
            messages = body.get("messages", [])
            provider = body.get("provider", DEFAULT_PROVIDER)
            model = body.get("model", "")
            session_id = self.headers.get("X-Session-ID", secrets.token_hex(8))

            if not messages:
                self._json_response({"error": "No messages"}, 400)
                return

            total_input = sum(len(m.get("content", "")) for m in messages)
            if total_input > MAX_CHAT_INPUT:
                self._json_response({
                    "error": "Input too large (%d chars, max %d)" % (total_input, MAX_CHAT_INPUT),
                }, 400)
                return

            if provider not in PROVIDERS:
                self._json_response({"error": "Unknown provider: %s" % provider}, 400)
                return
            if PROVIDERS[provider]["needs_key"] and not get_api_key(provider):
                self._json_response({
                    "error": "Set %s" % PROVIDERS[provider]["env_key"],
                }, 400)
                return

            sessions.get_or_create(session_id)
            for m in messages:
                if m.get("role") in ("user", "assistant") and m.get("content"):
                    sessions.add_message(session_id, m["role"], m["content"])

            self.send_response(200)
            for h, v in [
                ("Content-Type", "text/event-stream"),
                ("Cache-Control", "no-cache"),
                ("Connection", "keep-alive"),
                ("X-Accel-Buffering", "no"),
            ]:
                self.send_header(h, v)
            self._cors_headers()
            self.end_headers()

            try:
                loop = AgenticLoop(self, provider, model, session_id)
                if PROVIDERS.get(provider, {}).get("supports_tools"):
                    loop.run(messages)
                else:
                    loop.run_fallback(messages)
            except Exception as e:
                log.error("Chat error: %s", traceback.format_exc())
                self._sse("error", "Fatal: %s" % e)
            finally:
                try:
                    self.wfile.write(b"\n")
                    self.wfile.flush()
                except Exception:
                    pass
                self.close_connection = True

        except json.JSONDecodeError:
            self._json_response({"error": "Invalid JSON"}, 400)
        except Exception as e:
            log.error("Chat handler error: %s", e)
            try:
                self._json_response({"error": str(e)}, 500)
            except Exception:
                pass

    def _sse(self, event, data):
        payload = json.dumps({"type": event, "data": data})
        msg = "event: %s\ndata: %s\n\n" % (event, payload)
        try:
            self.wfile.write(msg.encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

# ── Graceful shutdown ──────────────────────────────────────────────────────
_httpd = None

def shutdown_handler(sig, frame):
    log.info("Shutting down...")
    if _httpd:
        threading.Thread(target=_httpd.shutdown, daemon=True).start()
    sys.exit(0)

# ── Main ───────────────────────────────────────────────────────────────────
_start_time = time.time()

class _HTTPServer(http.server.HTTPServer):
    allow_reuse_address = True


def main():
    global _httpd

    ollama_info = "running, %d model(s)" % len(discover_ollama_models()) if discover_ollama_running() else "not running"
    tools_count = len(ALL_TOOLS)
    agents_md = "loaded" if load_agents_md() else "not found"
    skills = load_skills()
    skills_info = "loaded" if skills else "none"

    log.info("ShellAgent v%s starting on http://%s:%s", VERSION, HOST, PORT)
    log.info("Tools: %d | Approval: %s | AGENTS.md: %s | Skills: %s",
             tools_count, APPROVAL_MODE, agents_md, skills_info)
    log.info("API secret: %s...", API_SECRET[:8])

    # --- Startup banner ---
    border = '+' + '-' * 56 + '+'
    print()
    print(border)
    print('| ShellAgent v%s' % VERSION)
    print('| Codex-style Agent -- 12 Tools + Full Autonomy')
    print(border)
    print('| Dashboard  : http://localhost:%s' % PORT)
    print('| Health     : http://localhost:%s/health' % PORT)
    print('| Tools      : %d tools (shell+web+files+git+grep+analyze+plan)' % tools_count)
    print('| Approval   : %s' % APPROVAL_MODE)
    print('| Auto-retry : %d per command' % MAX_RETRIES)
    print('| AGENTS.md  : %s' % agents_md)
    print('| Skills     : %s' % skills_info)
    print('| Sessions   : saved to %s' % SESSION_DIR)
    print('| Rate Limit : 60 req/min')
    print('| Max Body   : %dKB chat / %dKB input' % (MAX_REQ_BODY // 1000, MAX_CHAT_INPUT // 1000))
    print(border)
    print('| Providers:')
    print('|   OpenAI  : %s' % ("set" if OPENAI_API_KEY else "not set"))
    print('|   NVIDIA  : %s' % ("set" if NVIDIA_API_KEY else "not set"))
    print('|   Ollama  : %s' % ollama_info)
    print(border)
    print()
    if not any([OPENAI_API_KEY, NVIDIA_API_KEY]):
        print("  Set at least one API key:")
        print("    export OPENAI_API_KEY='sk-...'")
        print("    export NVIDIA_API_KEY='nvapi-...'")
        print("    Ollama works without a key if running locally\n")

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    _httpd = _HTTPServer((HOST, PORT), AgentHandler)
    _httpd.serve_forever()

if __name__ == "__main__":
    main()
