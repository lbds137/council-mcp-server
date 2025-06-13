# Migration Guide: v2.x to v3.0

This guide helps you migrate from Gemini MCP Server v2.x to v3.0, which introduces a modular architecture.

## Overview of Changes

### Architecture Changes

**v2.x (Monolithic)**
- Single 700+ line `server.py` file
- All tools defined as methods in one class
- Limited extensibility
- No caching or memory management

**v3.0 (Modular)**
- Modular architecture with clear separation of concerns
- Tool registry with automatic discovery
- Built-in caching and conversation memory
- Easy to add new tools
- Better testability

### New Features in v3.0

1. **Tool Registry** - Automatic tool discovery and registration
2. **Conversation Memory** - Maintains context across tool calls
3. **Response Caching** - LRU cache with TTL for expensive operations
4. **Tool Orchestrator** - Manages tool execution with proper context injection
5. **Debate Protocol** - Multi-agent debate capabilities
6. **Better Error Handling** - Consistent error reporting across all tools

## Migration Steps

### 1. Update Your Installation

```bash
# Pull latest changes
git pull origin main

# Update the installation
./scripts/update.sh
```

### 2. Environment Variables

No changes needed - v3.0 uses the same environment variables:
- `GEMINI_API_KEY` - Your Gemini API key
- `GEMINI_MODEL_PRIMARY` - Primary model (optional)
- `GEMINI_MODEL_FALLBACK` - Fallback model (optional)

### 3. Tool Names

All tool names remain the same:
- `ask_gemini`
- `gemini_code_review`
- `gemini_brainstorm`
- `gemini_test_cases`
- `gemini_explain`
- `synthesize_perspectives` (new in v3.0)

### 4. Usage in Claude

No changes needed - all tools work exactly the same way from Claude's perspective.

## For Developers

### Adding New Tools

In v2.x, you would add a method to the server class:
```python
def _new_tool(self, param: str) -> str:
    # Tool implementation
```

In v3.0, create a new tool class:
```python
# src/gemini_mcp/tools/my_tool.py
from .base import BaseTool
from ..models.base import ToolInput, ToolMetadata

class MyTool(BaseTool):
    def _get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_tool",
            description="What this tool does",
            tags=["relevant", "tags"],
            version="1.0.0"
        )
    
    def _get_input_schema(self):
        return {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Parameter"}
            },
            "required": ["param"]
        }
    
    async def _execute(self, input_data: ToolInput) -> str:
        # Tool implementation
        model_manager = input_data.context.get("model_manager")
        # ... rest of implementation
```

The tool will be automatically discovered and registered!

### Testing

v3.0 includes comprehensive test coverage:
```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=gemini_mcp

# Run specific test suite
python -m pytest tests/unit/test_ask_gemini_tool.py -v
```

### Architecture Benefits

1. **Separation of Concerns** - Each component has a single responsibility
2. **Extensibility** - Easy to add new tools without modifying core code
3. **Testability** - Each component can be tested in isolation
4. **Performance** - Built-in caching reduces API calls
5. **Maintainability** - Smaller, focused files are easier to understand

## Rollback Plan

If you need to rollback to v2.x:

```bash
# Checkout v2.x code
git checkout v2.1.0

# Reinstall
./scripts/install.sh

# Restart Claude Desktop
```

## Support

If you encounter issues:
1. Check the logs for detailed error messages
2. Ensure all dependencies are installed: `pip install -r requirements.txt`
3. Report issues at: https://github.com/your-repo/issues

## What's Next

Future v3.x releases will add:
- Streaming responses for long-form content
- Tool composition (tools calling other tools)
- Enhanced debate protocols
- Usage analytics and monitoring
- Plugin architecture for external tools