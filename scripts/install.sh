#!/bin/bash
# Smart install/update script for Gemini MCP Server v3

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$HOME/.claude-mcp-servers/gemini-collab"

# Determine if this is first install or update
if [ -d "$MCP_DIR" ]; then
    echo "🔄 Updating Gemini MCP Server v3"
    IS_UPDATE=true
else
    echo "🚀 Installing Gemini MCP Server v3"
    IS_UPDATE=false
fi

echo "   Source: $PROJECT_ROOT/server.py"
echo "   Target: $MCP_DIR"

# Check if bundled server exists, if not create it
if [ ! -f "$PROJECT_ROOT/server.py" ]; then
    echo "🔨 Bundled server not found, creating from modular source..."
    cd "$PROJECT_ROOT"
    python3 scripts/bundler.py
fi

# Create MCP directory if needed
if [ ! -d "$MCP_DIR" ]; then
    echo "📁 Creating MCP directory..."
    mkdir -p "$MCP_DIR"
fi

# Backup existing server if updating
if [ "$IS_UPDATE" = true ] && [ -f "$MCP_DIR/server.py" ]; then
    if ! cmp -s "$PROJECT_ROOT/server.py" "$MCP_DIR/server.py"; then
        echo "📦 Backing up current server..."
        cp "$MCP_DIR/server.py" "$MCP_DIR/server.backup.$(date +%Y%m%d_%H%M%S).py"
    fi
fi

# Deploy the server
if [ "$IS_UPDATE" = true ]; then
    echo "📝 Updating server..."
else
    echo "📦 Installing server..."
fi
cp "$PROJECT_ROOT/server.py" "$MCP_DIR/server.py"
chmod +x "$MCP_DIR/server.py"

# Copy requirements
echo "📋 Copying requirements..."
cp "$PROJECT_ROOT/requirements.txt" "$MCP_DIR/"

# Copy .env.example if .env doesn't exist
if [ ! -f "$MCP_DIR/.env" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    echo "📝 Creating .env file from template..."
    cp "$PROJECT_ROOT/.env.example" "$MCP_DIR/.env"
    echo "   ⚠️  Remember to add your GEMINI_API_KEY to $MCP_DIR/.env"
fi

echo ""
if [ "$IS_UPDATE" = true ]; then
    echo "✅ Update complete!"
    echo ""
    echo "📊 Changes:"
    echo "   - Server rebuilt from modular source"
    echo "   - Previous version backed up"
else
    echo "✅ Installation complete!"
    echo ""
    echo "🎉 Gemini MCP Server v3 is ready to use!"
fi

echo ""
echo "📋 Next steps:"
echo "   1. Ensure GEMINI_API_KEY is set in $MCP_DIR/.env"
echo "   2. Restart Claude Desktop"
echo "   3. Test with: mcp__gemini-collab__server_info"
