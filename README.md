# ShellAgent v7.3

**Codex-style agentic AI shell agent with 12 tools, web search, file ops, git, grep, code analysis, planning, auto-retry, process kill, conversation history, and zero dependencies.**

Like Codex CLI — the AI uses function calling with a full agentic loop: search the web, read/write files, run commands, grep code, analyze structure, validate changes, commit to git, and track progress with plans. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama** (local + cloud).

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Version](https://img.shields.io/badge/version-7.3-orange) ![Tools](https://img.shields.io/badge/tools-12-brightgreen)

## Installation (32-bit & 64-bit)

**Zero dependencies — Python 3.8+ stdlib only. No pip required.**

### Quick start
```bash
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent

export OPENAI_API_KEY="sk-..."
# OR
export NVIDIA_API_KEY="nvapi-..."

python3 app.py
# Open http://localhost:8765
```

### One-click launcher
```bash
./setup.sh
```

### Running on 32-bit ARM (Android phone, Raspberry Pi, etc.)
```bash
# 1. Install Python 3.8+ (use pkg on Termux)
pkg install python git

# 2. Clone the repo
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent

# 3. Run directly (no pip, no deps)
export OPENAI_API_KEY="sk-..."
python3 app.py

# 4. Open in browser: http://<phone-ip>:8765
```

### Git pull on 32-bit phone (divergent branches)
```bash
# If you get: "Your local changes would be overwritten by merge"
git stash
git pull
git stash pop

# If you get: "divergent branches"
git pull --rebase
```

## Features

### 12 Tools
| Tool | Category | What it does |
|---|---|---|
| `execute_shell_command` | ⚡ Shell | Run any shell command (auto-retry up to 3x) |
| `web_search` | 🔍 Web | Search via DuckDuckGo |
| `web_fetch` | 🌐 Web | Fetch and read any URL |
| `read_file` | 📖 Files | Read files with line numbers |
| `write_file` | ✏️ Files | Create or overwrite files (auto-creates dirs) |
| `list_directory` | 📁 Files | Explore directory structure |
| `grep_search` | 🔎 Search | Regex search across files (uses ripgrep when available) |
| `analyze_code` | 🔬 Analysis | Count lines, find functions/classes, identify imports |
| `update_plan` | 📋 Planning | Track task steps with pending/in-progress/completed |
| `git_commit` | 🔀 Git | Stage and commit changes |
| `validate_changes` | ✅ Validation | Run tests, lint, build |
| `list_git_changes` | 📊 Git | View status, log, diff, branch |

### v7.3 New Features
- **Process tracking & kill button** — stop stuck commands from the dashboard
- **Conversation history panel** — browse past sessions, search, load, delete
- **Custom NVIDIA model input** — set any NVIDIA NIM model in the web UI
- **Session export** — download conversations as JSON
- **Auto-cancellation** — kill cleanly stops the agent loop
- **Robust error handling** — no more hanging after iteration 1

### Full Codex-Style Features
- **AGENTS.md** — loads project instructions from AGENTS.md files in CWD and parents
- **Skills loading** — discovers `.shellagent/skills/*.md` files for task-specific knowledge
- **Plan tracking** — sidebar shows task plan with step-by-step progress
- **Session persistence** — conversations auto-saved to `~/.shellagent/sessions/`
- **Command history** — sidebar shows all tool calls with success/failure
- **Token tracking** — real-time token usage display
- **CWD selector** — click the folder icon to change working directory
- **Self-check** — AI verifies its work before finishing
- **Preamble** — brief visible update before heavy tool use
- **Auto-retry** — failed shell commands retry up to 3 times with backoff
- **No timeout** — commands run until completion (configurable, default 3600s)
- **Approval modes** — full-auto, auto-edit, ask
- **Rate limiting** — 60 requests per minute per IP
- **Thread safety** — concurrent users with lock-based session store
- **Graceful shutdown** — SIGINT/SIGTERM handled cleanly
- **Streaming UI** — real-time token-by-token output
- **Tool call display** — collapsible tool call blocks with status
- **Copy buttons** — copy code blocks and messages
- **Keyboard shortcuts** — / to focus, Escape to close

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_CMD_TIMEOUT` | `3600` | Per-command timeout (seconds) |
| `SHELLAGENT_MAX_ITERS` | `50` | Max agentic loop iterations |
| `SHELLAGENT_MAX_RETRIES` | `3` | Auto-retry count for failed commands |
| `SHELLAGENT_APPROVAL` | `full-auto` | Approval mode: full-auto, auto-edit, ask |
| `SHELLAGENT_CWD` | cwd | Working directory for commands |
| `SHELLAGENT_SESSIONS` | `~/.shellagent/sessions` | Session storage path |
| `SHELLAGENT_PROVIDER` | `openai` | Default provider |
| `SHELLAGENT_MODEL` | (provider default) | Default model override |
| `SHELLAGENT_SECRET` | (random) | API authentication secret |

## Supported Providers

### OpenAI
Uses the `gpt-4o` family. Models: gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, o3, o3-mini, o4-mini.

Set `OPENAI_API_KEY` and the agent gets full tool calling support.

### NVIDIA NIM
Access NVIDIA's hosted models via `https://integrate.api.nvidia.com/v1/chat/completions`. Supports tool calling.

Set `NVIDIA_API_KEY`. Models include Llama 3.3, Nemotron, Mistral, CodeStral, and Gemma.

**Custom NVIDIA model**: Click the provider dropdown → NVIDIA → select "Custom model" → enter any model name.

### Ollama (Local)
Runs models locally. Set `OLLAMA_HOST` (default: `http://localhost:11434`). No API key needed.

```bash
ollama pull llama3.2
export OLLAMA_HOST=http://localhost:11434
python3 app.py
```

## How It Works

```
User: "Search for Docker best practices and create a Dockerfile"

Agent:
  1. 📋 update_plan — outline steps
  2. 🔍 web_search — "Docker best practices 2026"
  3. 🌐 web_fetch — read the top article
  4. 📖 read_file — check if Dockerfile exists
  5. ✏️ write_file — create optimized Dockerfile
  6. 🔎 grep_search — verify patterns in the file
  7. 🔬 analyze_code — check file structure
  8. ✅ validate_changes — run hadolint
  9. 🔀 git_commit — "Add Dockerfile with best practices"
  10. 📋 update_plan — mark steps complete
  11. ✓ Summary with all changes
```

## Keyboard Shortcuts

- **Enter** — Send message
- **Shift+Enter** — Newline in input
- **/** — Focus input (when not focused)
- **Escape** — Close dropdowns / panels

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check with uptime, tools, provider status |
| `GET` | `/api/providers` | List available providers and models |
| `GET` | `/api/cwd` | Current working directory |
| `POST` | `/api/cwd` | Change working directory |
| `POST` | `/api/chat` | Send chat message (SSE streaming response) |
| `GET` | `/api/sessions` | List active sessions |
| `POST` | `/api/sessions/load` | Load a saved session |
| `POST` | `/api/sessions/delete` | Delete a session |
| `POST` | `/api/sessions/clear` | Clear messages in a session |
| `GET` | `/api/audit` | Recent tool call audit log |
| `POST` | `/api/kill` | Kill a running task by session_id |
| `GET` | `/api/export` | Export session as JSON download |

## Architecture

```
shellagent/
├── app.py              # 12 tools + agentic loop + web server (~1700 lines)
├── setup.sh            # One-click launcher
├── AGENTS.md           # Project instructions
├── templates/
│   └── index.html      # Dashboard with conversation panel
├── static/
│   ├── css/style.css   # Dark theme
│   └── js/app.js       # Streaming, plan, sessions, tool display
├── requirements.txt    # No dependencies
├── LICENSE
└── README.md
```

## Zero Dependencies

Pure Python 3.8+ stdlib. No pip install needed. Runs on 32-bit ARM (Termux, Raspberry Pi) and 64-bit systems.

## License

MIT
