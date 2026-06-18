# ShellAgent v7.4

**Full Codex CLI implementation — lightweight Python agent with 13 tools, apply_patch, goals, context compaction, command safety, session archiving, and zero dependencies.**

Like Codex CLI — the AI uses function calling with a full agentic loop: search the web, read/write files, run commands, apply patches, grep code, analyze structure, validate changes, track goals, review exits, manage git, and track progress with plans. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama**.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Version](https://img.shields.io/badge/version-7.4-orange) ![Tools](https://img.shields.io/badge/tools-13-brightgreen)

## Codex CLI Features (A-to-Z)

### Agentic Loop
- Iterative tool-calling with LLM function calling
- Auto-retry on failure (up to 3x with exponential backoff)
- No command timeout by default (configurable, default 3600s)
- Cancellation — stop any running task with the kill button
- Background server detection — auto-backgrounds long-lived processes
- Process group kill — properly kills child processes with shell=True

### 13 Tools

| Tool | Category | What it does |
|---|---|---|
| `execute_shell_command` | ⚡ Shell | Run any shell command (auto-retry, safety-checked) |
| `web_search` | 🔍 Web | Search via DuckDuckGo (with site_filter, max_results) |
| `web_fetch` | 🌐 Web | Fetch and read any URL |
| `read_file` | 📖 Files | Read files with line numbers |
| `write_file` | ✏️ Files | Create or overwrite files (auto-creates dirs) |
| `apply_patch` | 📝 Patch | Apply unified diff patches (surgical edits) |
| `list_directory` | 📁 Files | Explore directory structure |
| `grep_search` | 🔎 Search | Regex search across files (ripgrep when available) |
| `analyze_code` | 🔬 Analysis | Count lines, find functions/classes, identify imports |
| `update_plan` | 📋 Planning | Track task steps with pending/in-progress/completed |
| `update_goal` | 🎯 Goals | Mark goals complete or blocked |
| `review_exit` | ✅ Review | Self-check before finishing tasks |
| `git_commit` | 🔀 Git | Stage and commit changes |
| `validate_changes` | ✅ Validation | Run tests, lint, build |
| `list_git_changes` | 📊 Git | View status, log, diff, branch |

### Goal / Objective System
- `create_goal` with token budgets via API
- `update_goal` tool marks complete/blocked
- Continuation prompts with token usage tracking
- Active goal display on dashboard

### Planning
- Plan tracking with pending/in-progress/completed steps
- Visual sidebar display
- Auto-updates as the agent works

### AGENTS.md
- Loads project instructions from AGENTS.md files in CWD and parents
- Scoped instructions for subdirectories
- Precedence rules (deepest wins)

### Skills
- Discovers `.shellagent/skills/*.md` files
- Task-specific knowledge injection
- Loaded from user home and project directories

### Context Management
- Auto-compaction when conversation exceeds token limits
- Summarizes old messages while keeping recent context
- Continuation prompts for long-running goals

### Command Safety
- Blocks dangerous commands (rm -rf /, dd, mkfs, fork bombs, etc.)
- Self-kill protection — pkill -f won't kill ShellAgent
- Server auto-detection — `python3 -m http.server`, `flask run`, etc. backgrounded

### Session Management
- Auto-saved to `~/.shellagent/sessions/`
- Conversation history panel with search
- Session archive/unarchive
- Session delete
- Load from disk on reconnect
- Session export as JSON download

### Conversation Panel
- Browse past conversations
- Search by text or session ID
- Archive/delete conversations
- Click to reload any session
- Message count and timestamp display
- Export conversations as JSON

### Streaming UI
- Real-time token-by-token output via SSE
- Tool call blocks with status (running/success/failed)
- Iteration counter
- Token usage display
- Auto-scroll with manual override

### Plan Tracking
- Visual plan sidebar
- Step-by-step progress
- Status icons (○ pending, ◐ in-progress, ● completed)

### Provider Support
- **OpenAI** — GPT-4o family with full tool calling
- **NVIDIA NIM** — Llama, Nemotron, Mistral, CodeStral, Gemma with tool calling
- **Ollama** — local/remote models with tool calling support
- Custom model input — set any model name in the web UI

### Error Recovery
- Auto-retry with exponential backoff (3 attempts)
- Error diagnostics with API error body reading
- Graceful handling of broken pipes and connection resets
- Timeout handling with process group kill

### Security
- API secret authentication
- Rate limiting (60 req/min per IP)
- Command safety validation
- Self-kill prevention
- Request body size limits
- CORS headers for browser access

### Performance
- Zero dependencies — pure Python 3.8+ stdlib
- 32-bit and 64-bit support
- Gzip compression for static assets
- Thread safety with locking
- Session persistence with JSON serialization

### UI Features
- Dark theme with custom design
- Code block syntax highlighting
- Copy buttons for code and messages
- Markdown rendering
- Keyboard shortcuts (/ to focus, Escape to close)
- Responsive design
- Accessible with ARIA labels
- Loading dots, tool call animations

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

### Running on 32-bit ARM (Android phone via Termux, Raspberry Pi)
```bash
pkg install python git
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent
export OPENAI_API_KEY="sk-..."
python3 app.py
# Open http://<phone-ip>:8765
```

### Git pull (divergent branches fix)
```bash
# Local changes blocking pull
git stash
git pull
git stash pop

# Divergent branches
git pull --rebase
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_CMD_TIMEOUT` | `3600` | Per-command timeout (seconds) |
| `SHELLAGENT_MAX_ITERS` | `50` | Max agentic loop iterations |
| `SHELLAGENT_MAX_RETRIES` | `3` | Auto-retry count |
| `SHELLAGENT_APPROVAL` | `full-auto` | Approval mode |
| `SHELLAGENT_CWD` | cwd | Working directory |
| `SHELLAGENT_SESSIONS` | `~/.shellagent/sessions` | Session storage |
| `SHELLAGENT_PROVIDER` | `openai` | Default provider |
| `SHELLAGENT_MODEL` | (default) | Default model override |
| `SHELLAGENT_SECRET` | (random) | API authentication |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check |
| `GET` | `/api/providers` | List providers/models |
| `GET` | `/api/cwd` | Get working directory |
| `POST` | `/api/cwd` | Change working directory |
| `POST` | `/api/chat` | Send message (SSE stream) |
| `GET` | `/api/sessions` | List sessions |
| `POST` | `/api/sessions/load` | Load a session |
| `POST` | `/api/sessions/delete` | Delete a session |
| `POST` | `/api/sessions/archive` | Archive a session |
| `POST` | `/api/sessions/unarchive` | Unarchive a session |
| `POST` | `/api/sessions/clear` | Clear session messages |
| `POST` | `/api/goal` | Get/set active goal |
| `GET` | `/api/audit` | Tool call audit log |
| `POST` | `/api/kill` | Kill running task |
| `GET` | `/api/export` | Export session as JSON |
| `POST` | `/api/custom_model` | Set custom model |

## Architecture

```
shellagent/
├── app.py              # Full agent (~2000 lines)
├── setup.sh            # One-click launcher
├── AGENTS.md           # Project instructions
├── templates/
│   └── index.html      # Dashboard with all panels
├── static/
│   ├── css/style.css   # Dark theme with v7.4 additions
│   └── js/app.js       # Full frontend with streaming, goals, archives
├── requirements.txt    # No dependencies
├── LICENSE
└── README.md
```

## Zero Dependencies

Pure Python 3.8+ stdlib. No pip install. Runs on 32-bit ARM (Termux, Raspberry Pi) and 64-bit systems. Single-file backend (~2000 lines).

## License

MIT
