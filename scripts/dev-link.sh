#!/bin/bash
# Create a development symlink for live testing

set -e

echo "🔗 Setting up development symlink"
echo "================================"

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
MCP_DIR="$HOME/.claude-mcp-servers/gemini-collab"

# Check if MCP directory exists
if [ ! -d "$MCP_DIR" ]; then
    echo "❌ MCP directory not found. Run ./scripts/install.sh first!"
    exit 1
fi

# Backup original server.py if it exists and isn't already a symlink
if [ -f "$MCP_DIR/server.py" ] && [ ! -L "$MCP_DIR/server.py" ]; then
    echo "📦 Backing up original server.py..."
    mv "$MCP_DIR/server.py" "$MCP_DIR/server.original.py"
fi

# Create symlink
echo "🔗 Creating symlink to development version..."
ln -sf "$PROJECT_DIR/src/gemini_mcp/server.py" "$MCP_DIR/server.py"

echo ""
echo "✅ Development symlink created!"
echo ""
echo "Now changes to src/gemini_mcp/server.py will be reflected immediately."
echo "Just restart Claude Desktop to test changes."
echo ""
echo "To remove symlink and restore original:"
echo "  rm $MCP_DIR/server.py"
echo "  mv $MCP_DIR/server.original.py $MCP_DIR/server.py"
