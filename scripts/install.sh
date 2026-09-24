#!/bin/bash
# Install or update the Council MCP server.
#
# Installs the council package from this repo into its own venv and copies
# launcher.py beside it. The install is a snapshot of the working tree, not an
# editable install, so switching branches in the repo doesn't change the running
# server. INSTALLED records the commit that was deployed; to roll back, check out
# an earlier commit and run this script again.
#
# COUNCIL_MCP_DIR installs somewhere other than ~/.claude-mcp-servers/council
# (used to try an install without touching the live one).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="${COUNCIL_MCP_DIR:-$HOME/.claude-mcp-servers/council}"
VENV_DIR="$MCP_DIR/.venv"
PYTHON_VERSION="3.13"

if [ -d "$VENV_DIR" ]; then
    echo "🔄 Updating Council MCP Server in $MCP_DIR"
else
    echo "🚀 Installing Council MCP Server in $MCP_DIR"
fi

COMMIT="$(git -C "$PROJECT_ROOT" describe --always --dirty 2>/dev/null || echo unknown)"
if [[ "$COMMIT" == *-dirty ]]; then
    echo "   ⚠️  The working tree has uncommitted changes; they are installed too."
fi

mkdir -p "$MCP_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    if command -v uv >/dev/null 2>&1; then
        # uv's own standalone Python, so an OS Python upgrade can't break the server.
        # --seed adds pip, which the install below uses.
        uv venv --managed-python --python "$PYTHON_VERSION" --seed "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
    fi
fi

echo "📦 Installing council and its dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
# pip reinstalls from a directory even when the version number hasn't changed
"$VENV_DIR/bin/pip" install --quiet "$PROJECT_ROOT"
cp "$PROJECT_ROOT/launcher.py" "$MCP_DIR/launcher.py"

# Fail here, not at the next reconnect, if the install can't even import
"$VENV_DIR/bin/python" -c "import council.main"

printf 'commit: %s\ninstalled: %s\n' "$COMMIT" "$(date '+%Y-%m-%d %H:%M:%S %Z')" \
    > "$MCP_DIR/INSTALLED"

if [ ! -f "$MCP_DIR/.env" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    echo "📝 Creating .env from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$MCP_DIR/.env"
fi

echo ""
echo "✅ Installed $COMMIT"
echo ""
echo "📋 Next steps:"
echo "   - First install: store your OpenRouter key with scripts/set-secret.sh OPENROUTER_API_KEY,"
echo "     then register the server with Claude Code:"
echo "       claude mcp add council -s user -- $VENV_DIR/bin/python $MCP_DIR/launcher.py"
echo "     (Claude Desktop: command \"$VENV_DIR/bin/python\", args [\"$MCP_DIR/launcher.py\"])"
echo "   - Update: reconnect council in each open Claude Code session (/mcp → council → Reconnect)"
