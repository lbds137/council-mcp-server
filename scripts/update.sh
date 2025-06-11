#!/bin/bash
# Update script for Gemini MCP Server - syncs development changes to MCP location

set -e

echo "🔄 Updating Gemini MCP Server"
echo "============================="

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
MCP_DIR="$HOME/.claude-mcp-servers/gemini-collab"

# Check if MCP directory exists
if [ ! -d "$MCP_DIR" ]; then
    echo "❌ MCP directory not found. Run ./scripts/install.sh first!"
    exit 1
fi

# Backup current server if different
if [ -f "$MCP_DIR/server.py" ]; then
    if ! cmp -s "$PROJECT_DIR/src/gemini_mcp/server.py" "$MCP_DIR/server.py"; then
        echo "📦 Backing up current server..."
        cp "$MCP_DIR/server.py" "$MCP_DIR/server.backup.$(date +%Y%m%d_%H%M%S).py"
    fi
fi

# Copy updated files
echo "📝 Updating server files..."
cp "$PROJECT_DIR/src/gemini_mcp/server.py" "$MCP_DIR/"
cp "$PROJECT_DIR/requirements.txt" "$MCP_DIR/"
cp "$PROJECT_DIR/.env.example" "$MCP_DIR/"

# Update documentation
cp "$PROJECT_DIR/README.md" "$MCP_DIR/"
if [ -f "$PROJECT_DIR/docs/DUAL_MODEL_CONFIGURATION.md" ]; then
    cp "$PROJECT_DIR/docs/DUAL_MODEL_CONFIGURATION.md" "$MCP_DIR/"
fi

# Show what changed
echo ""
echo "📊 Update summary:"
echo "- Server code updated from development version"
echo "- Documentation synced"
echo "- Your .env configuration preserved"

# Check if server is registered
if command -v claude &> /dev/null; then
    if claude mcp list | grep -q "gemini-collab"; then
        echo "✅ MCP registration intact"
    else
        echo "⚠️  MCP not registered. Run: claude mcp add --scope user gemini-collab python3 $MCP_DIR/server.py"
    fi
fi

echo ""
echo "✅ Update complete!"
echo ""
echo "Note: Restart Claude Desktop to use the updated server."
echo "Test with: mcp__gemini-collab__server_info"