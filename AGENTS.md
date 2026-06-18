# ShellAgent Project Instructions

## What is ShellAgent
ShellAgent v7.0 is a lightweight Codex-style agentic AI shell agent with a web dashboard. Single-file Python backend, zero external dependencies.

## Build & Run
```bash
python3 app.py           # Starts on http://localhost:8765
```

## Code Style
- Python 3.8+ stdlib only (no pip dependencies)
- 32-bit and 64-bit compatible
- Single file backend (`app.py`) — keep it self-contained
- Dark theme web dashboard (HTML/CSS/JS in `templates/` and `static/`)
- All tool calls stream via SSE to the frontend

## Tools (12 total)
- execute_shell_command, web_search, web_fetch, read_file, write_file
- list_directory, grep_search, analyze_code, update_plan
- git_commit, validate_changes, list_git_changes

## Providers
- OpenAI (primary, native tool calling)
- NVIDIA NIM (native tool calling)
- Ollama (local/remote, native tool calling)

## Architecture Principles
- No external Python packages — stdlib only
- Thread-safe session store with locking
- Auto-retry on command failure (up to 3 attempts)
- No command timeout by default (configurable)
- Full-auto approval mode — no confirmation needed
- Streaming SSE responses for real-time feedback

## Testing
```bash
python3 -c "import app; print('OK')"
```
