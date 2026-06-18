#!/bin/bash
# ShellAgent v7.0 — One-click launcher
set -e

cd "$(dirname "$0")"

echo "⚡ ShellAgent v7.0"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install Python 3.8+."
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PYTHON_VER"

# Check API keys
if [ -n "$OPENAI_API_KEY" ]; then
    echo "✓ OpenAI API key set"
fi
if [ -n "$NVIDIA_API_KEY" ]; then
    echo "✓ NVIDIA API key set"
fi
if command -v ollama &>/dev/null; then
    echo "✓ Ollama found"
fi

echo ""
PORT=${SHELLAGENT_PORT:-8765}
echo "🚀 Starting on http://localhost:$PORT"
echo "   Press Ctrl+C to stop"
echo ""

python3 app.py
