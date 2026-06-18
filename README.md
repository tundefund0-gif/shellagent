# ShellAgent

**Lightweight AI-powered shell command agent with a web dashboard.**

Chat with an AI that can execute shell commands on your machine in real-time. Zero external dependencies — runs on Python 3.8+ stdlib only. Supports 32-bit and 64-bit systems.

![ShellAgent](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-32%2F64--bit-orange)

## Features

- **Natural language to shell commands** — describe what you want, AI runs it
- **Real-time streaming** — SSE-based streaming for instant responses
- **Auto-execute mode** — commands run automatically, or switch to manual
- **Web dashboard** — clean dark UI inspired by modern CLI tools
- **Zero dependencies** — Python 3.8+ stdlib only, nothing to install
- **32-bit support** — works on i386, ARM, x86_64, and more
- **Lightweight** — single Python file, ~200 lines of code
- **System context** — auto-detects OS, disk, memory for smarter responses

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/shellagent.git
cd shellagent

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Run
python3 app.py
```

Then open **http://localhost:8765** in your browser.

Or use the one-click setup:

```bash
export OPENAI_API_KEY="sk-..."
./setup.sh
```

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `SHELLAGENT_MODEL` | `gpt-4o` | Model to use |
| `SHELLAGENT_PORT` | `8765` | Dashboard port |
| `SHELLAGENT_HOST` | `0.0.0.0` | Bind address |
| `SHELLAGENT_TIMEOUT` | `30` | Command timeout (seconds) |
| `SHELLAGENT_CWD` | current dir | Working directory for commands |

## Architecture

```
shellagent/
├── app.py              # Python stdlib HTTP server + SSE + shell exec
├── setup.sh            # One-click launcher
├── templates/
│   └── index.html      # Dashboard UI
├── static/
│   ├── css/style.css   # Dark theme styles
│   └── js/app.js       # SSE streaming + markdown rendering
├── requirements.txt    # No dependencies needed
├── LICENSE
└── README.md
```

## How It Works

1. User types a message in the web dashboard
2. Message is sent to OpenAI API with system context (OS, disk, memory)
3. AI responds with text and bash code blocks
4. Code blocks are extracted and optionally executed
5. Command output is streamed back to the dashboard in real-time

## Security

- Commands run in the server's working directory
- Set `SHELLAGENT_CWD` to limit where commands execute
- Shell timeout prevents runaway processes
- Auto-execute can be disabled via the dashboard toggle

## License

MIT
