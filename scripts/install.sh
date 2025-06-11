#!/bin/bash
# Install script for Gemini MCP Server

set -e

echo "🚀 Installing Gemini MCP Server"
echo "==============================="

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
MCP_DIR="$HOME/.claude-mcp-servers/gemini-collab"

# Create MCP directory if it doesn't exist
echo "📁 Creating MCP directory..."
mkdir -p "$MCP_DIR"

# Copy necessary files
echo "📦 Copying server files..."
cp "$PROJECT_DIR/src/gemini_mcp/server.py" "$MCP_DIR/"
cp "$PROJECT_DIR/requirements.txt" "$MCP_DIR/"
cp "$PROJECT_DIR/.env.example" "$MCP_DIR/"

# Copy README files
cp "$PROJECT_DIR/README.md" "$MCP_DIR/"
if [ -f "$PROJECT_DIR/docs/DUAL_MODEL_CONFIGURATION.md" ]; then
    cp "$PROJECT_DIR/docs/DUAL_MODEL_CONFIGURATION.md" "$MCP_DIR/"
fi

# Check if .env exists
if [ ! -f "$MCP_DIR/.env" ]; then
    echo "📝 Creating .env file from template..."
    cp "$MCP_DIR/.env.example" "$MCP_DIR/.env"
    echo "⚠️  Please edit $MCP_DIR/.env and add your GEMINI_API_KEY"
else
    echo "✅ Existing .env file preserved"
fi

# Register with Claude
echo "🔧 Registering with Claude..."
if command -v claude &> /dev/null; then
    # Remove old registration if exists
    claude mcp remove gemini-collab 2>/dev/null || true
    
    # Add new registration
    claude mcp add --scope user gemini-collab python3 "$MCP_DIR/server.py"
    echo "✅ Registered with Claude CLI"
else
    echo "⚠️  Claude CLI not found. Manual registration required:"
    echo "   claude mcp add --scope user gemini-collab python3 $MCP_DIR/server.py"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit $MCP_DIR/.env with your GEMINI_API_KEY"
echo "2. Restart Claude Desktop"
echo "3. Test with: mcp__gemini-collab__server_info"
echo ""
echo "For development:"
echo "- Make changes in: $PROJECT_DIR"
echo "- Update MCP with: ./scripts/update.sh"