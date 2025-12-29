#!/bin/bash
#
# Install git hooks for council-mcp-server
#
# Usage: ./scripts/install-hooks.sh
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_SOURCE="$PROJECT_ROOT/hooks"
HOOKS_DEST="$PROJECT_ROOT/.git/hooks"

echo -e "${BLUE}Installing git hooks...${NC}"

# Check if hooks directory exists
if [ ! -d "$HOOKS_SOURCE" ]; then
    echo "Error: hooks directory not found at $HOOKS_SOURCE"
    exit 1
fi

# Check if .git directory exists
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "Error: .git directory not found. Are you in a git repository?"
    exit 1
fi

# Create .git/hooks if it doesn't exist
mkdir -p "$HOOKS_DEST"

# Copy all hooks
for hook in "$HOOKS_SOURCE"/*; do
    if [ -f "$hook" ]; then
        hook_name=$(basename "$hook")
        cp "$hook" "$HOOKS_DEST/$hook_name"
        chmod +x "$HOOKS_DEST/$hook_name"
        echo -e "${GREEN}  Installed: $hook_name${NC}"
    fi
done

# Also ensure pre-commit hooks are installed (from .pre-commit-config.yaml)
if command -v pre-commit &> /dev/null; then
    echo -e "${BLUE}Installing pre-commit hooks...${NC}"
    cd "$PROJECT_ROOT"
    pre-commit install
    echo -e "${GREEN}  Pre-commit hooks installed${NC}"
else
    echo -e "${BLUE}Note: pre-commit not found. Install with: pip install pre-commit${NC}"
fi

echo ""
echo -e "${GREEN}Git hooks installed successfully!${NC}"
echo ""
echo "Hooks installed:"
echo "  - pre-commit: Runs formatting and linting on staged files"
echo "  - pre-push: Runs full test suite and type checking before push"
