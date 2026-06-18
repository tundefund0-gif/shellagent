# ShellAgent v5.0

**Definitive agentic AI agent with 10 tools, web search, file ops, git integration, plan tracking, and session persistence.**

Like Codex — the AI uses function calling with a full agentic loop: search the web, read/write files, run commands, validate changes, commit to git, and track progress with plans. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama**.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Version](https://img.shields.io/badge/version-5.0-orange) ![Tools](https://img.shields.io/badge/tools-10-brightgreen)

## 10 Tools

| Tool | Category | What it does |
|---|---|---|
| `execute_shell_command` | ⚡ Shell | Run any shell command |
| `web_search` | 🔍 Web | Search via DuckDuckGo |
| `web_fetch` | 🌐 Web | Fetch and read any URL |
| `read_file` | 📖 Files | Read files from disk |
| `write_file` | ✏️ Files | Create or overwrite files |
| `list_directory` | 📁 Files | Explore directory structure |
| `update_plan` | 📋 Planning | Track task steps and status |
| `git_commit` | 🔀 Git | Stage and commit changes |
| `validate_changes` | ✅ Validation | Run tests, lint, build |
| `list_git_changes` | 📊 Git | View status, log, diff |

## Codex Features

- **AGENTS.md** — loads project instructions from AGENTS.md files in CWD and parents
- **Plan tracking** — sidebar shows task plan with step-by-step progress
- **Session persistence** — conversations auto-saved to `~/.shellagent/sessions/`
- **Command history** — sidebar shows all tool calls with success/failure
- **Token tracking** — real-time token usage display
- **CWD selector** — click the folder icon to change working directory
- **Self-check** — AI verifies its work before finishing
- **Preamble** — brief visible update before heavy tool use
- **Outcome-first prompting** — defines goals, lets AI choose the path

## Quick Start

```bash
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent

export OPENAI_API_KEY="sk-..."
python3 app.py
# Open http://localhost:8765
```

## Supported Providers

| Provider | Tool Calling | Setup |
|---|---|---|
| **OpenAI** | ✅ | `export OPENAI_API_KEY="sk-..."` |
| **NVIDIA NIM** | ✅ | `export NVIDIA_API_KEY="nvapi-..."` |
| **Ollama** (local) | ✅ | Install [Ollama](https://ollama.ai), run `ollama serve` |
| **Ollama** (remote) | ✅ | `export OLLAMA_HOST="http://server:11434"` |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_CMD_TIMEOUT` | `3600` | Per-command timeout (seconds) |
| `SHELLAGENT_MAX_ITERS` | `50` | Max agentic loop iterations |
| `SHELLAGENT_APPROVAL` | `full-auto` | Approval mode: full-auto, auto-edit, ask |
| `SHELLAGENT_CWD` | cwd | Working directory for commands |
| `SHELLAGENT_SESSIONS` | `~/.shellagent/sessions` | Session storage path |

## How It Works

```
User: "Search for Docker best practices and create a Dockerfile"

Agent:
  1. 📋 update_plan — outline steps
  2. 🔍 web_search — "Docker best practices 2026"
  3. 🌐 web_fetch — read the top article
  4. 📖 read_file — check if Dockerfile exists
  5. ✏️ write_file — create optimized Dockerfile
  6. ✅ validate_changes — run hadolint
  7. 🔀 git_commit — "Add Dockerfile with best practices"
  8. 📋 update_plan — mark steps complete
  9. ✓ Summary with all changes
```

## Keyboard Shortcuts

- **Enter** — Send message
- **Shift+Enter** — Newline in input

## Architecture

```
shellagent/
├── app.py              # 10 tools + agentic loop + web server
├── setup.sh            # One-click launcher
├── AGENTS.md           # Project instructions
├── templates/
│   └── index.html      # Dashboard with sidebar
├── static/
│   ├── css/style.css   # Dark theme with sidebar
│   └── js/app.js       # Plan tracker, history, sessions
├── requirements.txt    # No dependencies
├── LICENSE
└── README.md
```

## Zero Dependencies

Pure Python 3.8+ stdlib. No pip install needed. 32-bit and 64-bit support.

## License

MIT
