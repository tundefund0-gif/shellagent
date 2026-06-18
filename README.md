# ShellAgent v3.0

**Agentic AI shell command agent with tool calling, auto-retry, and no timeouts.**

Like Codex — the AI calls a tool to execute shell commands, sees results inline, decides to retry or continue, and loops autonomously until the task is done. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama** (local + remote).

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Arch](https://img.shields.io/badge/arch-32%2F64--bit-orange)

## What's New in v3.0

- **Tool calling architecture** — AI uses `execute_shell_command` tool (not code blocks)
- **No command timeout** — commands run until they finish (default: 1 hour)
- **Auto-retry on failure** — AI sees errors, diagnoses, and retries automatically
- **Agentic loop** — multi-step autonomous execution (up to 30 iterations)
- **Iteration tracking** — see which iteration the agent is on in real-time
- **Streaming tool results** — watch commands execute as they happen
- **Exit code display** — see success/failure status for each command

## How It Works (Codex-style)

```
User: "Install nginx and configure it as a reverse proxy"

Agent iterates:
  1. → execute_shell_command("apt update && apt install -y nginx")
  1. ← [exit 0] Reading package lists... Done.
  2. → execute_shell_command("cat /etc/nginx/nginx.conf")
  2. ← [exit 0] user http { ... }
  3. → execute_shell_command("sed -i 's/.../' /etc/nginx/nginx.conf")
  3. ← [exit 0]
  4. → execute_shell_command("systemctl restart nginx && systemctl status nginx")
  4. ← [exit 0] Active: active (running)...
  5. → (no more tool calls — task complete)
  5. ✓ Summary: "Nginx installed and configured as reverse proxy on port 80."
```

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
|----------|:---:|---|
| **OpenAI** | ✅ | `export OPENAI_API_KEY="sk-..."` |
| **NVIDIA NIM** | ✅ | `export NVIDIA_API_KEY="nvapi-..."` |
| **Ollama** (local) | ✅ | Install [Ollama](https://ollama.ai), run `ollama serve` |
| **Ollama** (remote) | ✅ | `export OLLAMA_HOST="http://server:11434"` |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_CMD_TIMEOUT` | `3600` | Per-command timeout (seconds). Set high for long-running commands |
| `SHELLAGENT_MAX_ITERS` | `30` | Max agentic loop iterations |
| `SHELLAGENT_CWD` | cwd | Working directory for commands |
| `SHELLAGENT_PROVIDER` | `openai` | Default provider |
| `SHELLAGENT_MODEL` | *(auto)* | Default model |

## Zero Dependencies

Pure Python 3.8+ stdlib. No pip install needed. Works on 32-bit and 64-bit systems.

## License

MIT
