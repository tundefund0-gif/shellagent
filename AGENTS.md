# ShellAgent Project Guidelines

## Architecture
- Single-file Python backend (`app.py`) using only stdlib
- Web dashboard served by the same process
- Tool-calling agentic loop (Codex-style)

## Code Style
- Python 3.8+ compatible
- No external dependencies
- Functions prefixed with `_` are internal helpers
- Tool implementations are standalone functions dispatched via `TOOL_DISPATCH`

## Testing
- Run `python3 -c "import app; print('OK')"` for quick syntax check
- All tools have standalone test functions

## Deployment
- Single command: `python3 app.py`
- All config via environment variables
- Dashboard at http://localhost:8765
