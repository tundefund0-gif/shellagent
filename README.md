# ShellAgent v2.0

**AI-powered shell command agent with multi-provider support and web dashboard.**

Chat with AI models that execute shell commands on your machine autonomously — no confirmation needed. Supports **OpenAI**, **NVIDIA NIM**, and **Ollama** (local + remote). Zero external dependencies. 32-bit and 64-bit systems.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-32%2F64--bit-orange)

## Features

- **Multi-provider support** — OpenAI, NVIDIA NIM, Ollama (local & remote)
- **Zero-confirmation execution** — AI runs commands immediately, like Codex
- **Auto-execute toggle** — switch between auto and manual modes
- **Real-time streaming** — SSE-based token-by-token responses
- **Model discovery** — auto-discovers local Ollama models
- **Command output analysis** — AI summarizes results after execution
- **Zero dependencies** — pure Python 3.8+ stdlib
- **32-bit support** — runs on i386, ARM, x86_64, and more
- **Clean dark UI** — polished web dashboard with provider switching

## Quick Start

```bash
# Clone
git clone https://github.com/tundefund0-gif/shellagent.git
cd shellagent

# Set at least one provider key
export OPENAI_API_KEY="sk-..."        # OpenAI
export NVIDIA_API_KEY="nvapi-..."     # NVIDIA NIM
# Ollama needs no key if running locally

# Run
python3 app.py
# Open http://localhost:8765
```

Or use the one-click launcher:

```bash
./setup.sh
```

## Supported Providers

### OpenAI
Set `OPENAI_API_KEY`. Models: `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `o3`, `o3-mini`, `o4-mini`.

### NVIDIA NIM
Get an API key at [build.nvidia.com](https://build.nvidia.com). Set `NVIDIA_API_KEY`.
Models: `meta/llama-3.3-70b-instruct`, `nvidia/nemotron-ultra-253b`, `deepseek-r1`, `codestral`, and more.

### Ollama (Local)
Install [Ollama](https://ollama.ai). Run `ollama serve`. No API key needed.
Models auto-discovered: `llama3`, `mistral`, `codellama`, `deepseek-r1`, etc.

### Ollama (Remote)
```bash
export OLLAMA_HOST="http://your-server:11434"
# Optional: export OLLAMA_API_KEY="..."
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key |
| `NVIDIA_API_KEY` | *(empty)* | NVIDIA NIM API key |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_API_KEY` | *(empty)* | Optional Ollama auth |
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_TIMEOUT` | `60` | Command timeout (seconds) |
| `SHELLAGENT_CWD` | current dir | Working directory |
| `SHELLAGENT_PROVIDER` | `openai` | Default provider |
| `SHELLAGENT_MODEL` | *(auto)* | Default model |

## Architecture

```
shellagent/
├── app.py              # Multi-provider HTTP server + SSE + shell exec
├── setup.sh            # One-click launcher
├── templates/
│   └── index.html      # Dashboard UI
├── static/
│   ├── css/style.css   # Dark theme
│   └── js/app.js       # Provider switching + streaming + markdown
├── requirements.txt    # No dependencies
├── LICENSE
└── README.md
```

## How It Works

1. User selects provider + model in the dashboard
2. Types a message describing what they want done
3. Message is streamed to the chosen LLM with system context
4. AI responds with explanations + bash code blocks
5. Code blocks are auto-extracted and executed immediately
6. Command output is displayed in terminal-style blocks
7. AI gets results back and provides a summary

## License

MIT
