#!/bin/bash
set -e
echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║        ShellAgent v5.0 — Quick Setup                 ║"
echo "║  10 tools · Shell + Web + Files + Git + Planning     ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
done

if [ -z "$PYTHON" ]; then echo "❌ Python 3.8+ required"; exit 1; fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PY_VER ($(which $PYTHON))"
echo "✓ Arch: $(uname -m)"
echo ""

# Check providers
[ -n "$OPENAI_API_KEY" ] && echo "✓ OpenAI: key set" || echo "  OpenAI: set OPENAI_API_KEY"
[ -n "$NVIDIA_API_KEY" ] && echo "✓ NVIDIA: key set" || echo "  NVIDIA: set NVIDIA_API_KEY"
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then echo "✓ Ollama: running"; else echo "  Ollama: not detected"; fi

# Check AGENTS.md
[ -f "AGENTS.md" ] && echo "✓ AGENTS.md: found" || echo "  AGENTS.md: not found (optional)"

# Create session dir
mkdir -p ~/.shellagent/sessions 2>/dev/null
echo "✓ Sessions: ~/.shellagent/sessions"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting ShellAgent v5.0 on http://localhost:8765"
echo "  10 tools · full-auto · no confirmation needed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
exec $PYTHON app.py
