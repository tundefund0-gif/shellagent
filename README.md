# ShellAgent v7.1

**Codex-style agentic AI shell agent with 12 tools, web search, file ops, git, grep, code analysis, planning, auto-retry, and zero dependencies.**

Like Codex — the AI uses function calling with a full agentic loop: search the web, read/write files, run commands, grep code, analyze structure, validate changes, commit to git, and track progress with plans. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama**.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Version](https://img.shields.io/badge/version-7.0-orange) ![Tools](https://img.shields.io/badge/tools-12-brightgreen)

## 12 Tools

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

## Codex Features

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

## Quick Start

```bash
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent

export OPENAI_API_KEY="sk-..."
python3 app.py
# Open http://localhost:8765
```

One-click launcher:
```bash
./setup.sh
```

## Supported Providers

| Provider | Tool Calling | Setup |
|---|---|---|
| **OpenAI** | ✅ Native | `export OPENAI_API_KEY="sk-..."` |
| **NVIDIA NIM** | ✅ Native | `export NVIDIA_API_KEY="nvapi-..."` |
| **Ollama** (local) | ✅ Native | Install [Ollama](https://ollama.ai), run `ollama serve` |
| **Ollama** (remote) | ✅ Native | `export OLLAMA_HOST="http://server:11434"` |

### NVIDIA NIM Models
- `meta/llama-3.3-70b-instruct`
- `meta/llama-3.1-8b-instruct`
- `meta/llama-3.1-70b-instruct`
- `nvidia/llama-3.3-nemotron-super-49b-v1`
- `nvidia/llama-3.1-nemotron-ultra-253b-v1`
- `mistralai/mistral-large-2-instruct`
- `mistralai/codestral-2405`
- `google/gemma-2-27b-it`
- `deepseek-ai/deepseek-r1`

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
- **Escape** — Close dropdowns

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
| `GET` | `/api/audit` | Recent tool call audit log |

## Architecture

```
shellagent/
├── app.py              # 12 tools + agentic loop + web server (~1400 lines)
├── setup.sh            # One-click launcher
├── AGENTS.md           # Project instructions
├── templates/
│   └── index.html      # Dashboard with sidebar
├── static/
│   ├── css/style.css   # Dark theme with sidebar
│   └── js/app.js       # Plan tracker, history, sessions, streaming
├── requirements.txt    # No dependencies
├── LICENSE
└── README.md
```

## Zero Dependencies

Pure Python 3.8+ stdlib. No pip install needed. 32-bit and 64-bit support.

## License

MIT
