#!/bin/bash
set -e
echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║      ShellAgent v2.0 — Quick Setup            ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "❌ Python 3.8+ is required."
  exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ARCH=$(uname -m)
echo "✓ Python $PY_VER ($(which $PYTHON))"
echo "✓ Architecture: $ARCH"
echo ""

# Provider status
[ -n "$OPENAI_API_KEY" ] && echo "✓ OpenAI: key set" || echo "  OpenAI: set OPENAI_API_KEY"
[ -n "$NVIDIA_API_KEY" ] && echo "✓ NVIDIA: key set" || echo "  NVIDIA: set NVIDIA_API_KEY"

if command -v curl &>/dev/null; then
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "✓ Ollama: running locally"
  else
    echo "  Ollama: not detected (install from ollama.ai)"
  fi
else
  echo "  Ollama: can't check (curl not found)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Starting ShellAgent on http://localhost:8765"
echo "  Press Ctrl+C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
exec $PYTHON app.py
