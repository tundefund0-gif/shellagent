#!/bin/bash
set -e
echo "╔════════════════════════════════════════╗"
echo "║      ShellAgent - Quick Setup          ║"
echo "╚════════════════════════════════════════╝"

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "❌ Python 3.8+ is required. Please install Python first."
  exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Found Python $PY_VER at $(which $PYTHON)"

# Check for 32-bit support
ARCH=$(uname -m)
echo "✓ Architecture: $ARCH"

if [ -z "$OPENAI_API_KEY" ]; then
  echo ""
  echo "⚠  No OPENAI_API_KEY found in environment."
  echo "   Set it with: export OPENAI_API_KEY='sk-...'"
  echo ""
fi

echo ""
echo "Starting ShellAgent on http://localhost:8765"
echo "Press Ctrl+C to stop"
echo ""
exec $PYTHON app.py
