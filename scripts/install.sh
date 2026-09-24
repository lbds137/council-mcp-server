#!/bin/bash
# Install or update the Council MCP server.
#
# Installs the council package, as of the commit checked out in this repo, into
# its own venv, and puts launcher.py from that commit beside it. It installs the
# commit straight from git, so uncommitted edits and leftovers in build/ never
# ship, and INSTALLED names exactly what is running. To roll back, check out an
# earlier commit and run this script again.
#
# COUNCIL_MCP_DIR installs somewhere other than ~/.claude-mcp-servers/council
# (used to try an install without touching the live one).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="${COUNCIL_MCP_DIR:-$HOME/.claude-mcp-servers/council}"
VENV_DIR="$MCP_DIR/.venv"
PYTHON_VERSION="3.13"

if ! COMMIT="$(git -C "$PROJECT_ROOT" rev-parse --verify HEAD 2>/dev/null)"; then
    echo "❌ $PROJECT_ROOT is not a git checkout with a commit; install.sh deploys commits." >&2
    exit 1
fi
SHORT="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD)"
if [ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]; then
    echo "   ⚠️  The repo has uncommitted changes. They are NOT installed: commit them first"
    echo "      if they should ship. Installing $SHORT as committed."
fi

if [ -d "$VENV_DIR" ]; then
    echo "🔄 Updating Council MCP Server in $MCP_DIR"
else
    echo "🚀 Installing Council MCP Server in $MCP_DIR"
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

echo "📦 Installing council $SHORT and its dependencies..."
SOURCE="git+file://$PROJECT_ROOT@$COMMIT"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
# The first command installs any missing dependencies. pip counts the same version
# from git as already installed, so the second replaces council itself every time.
"$VENV_DIR/bin/pip" install --quiet "$SOURCE"
"$VENV_DIR/bin/pip" install --quiet --force-reinstall --no-deps "$SOURCE"
# Via a temporary name, so a failed git show can't leave the live launcher empty
git -C "$PROJECT_ROOT" show "$COMMIT:launcher.py" > "$MCP_DIR/launcher.py.new"
mv "$MCP_DIR/launcher.py.new" "$MCP_DIR/launcher.py"

# Fail here, not at the next reconnect, if the install can't even import
"$VENV_DIR/bin/python" -c "import council.main"

printf 'commit: %s\ninstalled: %s\n' "$COMMIT" "$(date '+%Y-%m-%d %H:%M:%S %Z')" \
    > "$MCP_DIR/INSTALLED"

if [ ! -f "$MCP_DIR/.env" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    echo "📝 Creating .env from .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$MCP_DIR/.env"
fi

echo ""
echo "✅ Installed $SHORT"
echo ""
echo "📋 Next steps:"
echo "   - First install: store your OpenRouter key with scripts/set-secret.sh OPENROUTER_API_KEY,"
echo "     then register the server with Claude Code:"
echo "       claude mcp add council -s user -- $VENV_DIR/bin/python $MCP_DIR/launcher.py"
echo "     (Claude Desktop: command \"$VENV_DIR/bin/python\", args [\"$MCP_DIR/launcher.py\"])"
echo "   - Update: reconnect council in each open Claude Code session (/mcp → council → Reconnect)"
