# CLAUDE.md - Council MCP Server

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@~/.claude/CLAUDE.md

## Project Overview

**Council** is a Model Context Protocol (MCP) server that enables Claude to collaborate with multiple AI models via OpenRouter. It provides a provider-agnostic way for AI-to-AI collaboration on complex tasks, allowing access to Gemini, GPT, Claude, Llama, and many other models.

### Key Features
- **Multi-Model Support**: Access 100+ models via OpenRouter (Gemini, GPT, Claude, Llama, Mistral, etc.)
- **Dynamic Model Discovery**: List and filter available models by provider, capability, or pricing
- **Per-Request Model Override**: Use different models for different tasks
- **Multiple Collaboration Tools**: Code review, brainstorming, test generation, explanations
- **Response Caching**: Automatic caching for repeated queries

## Available MCP Tools

Since this MCP server is already running, you can use these tools directly:

### Core Tools
- `mcp__council__ask` - Ask any model general questions
- `mcp__council__code_review` - Get code review
- `mcp__council__brainstorm` - Brainstorm ideas with AI
- `mcp__council__test_cases` - Generate test cases
- `mcp__council__explain` - Get explanations
- `mcp__council__synthesize_perspectives` - Combine multiple viewpoints

### Model Management
- `mcp__council__server_info` - Check server status and current model
- `mcp__council__list_models` - List available models with filtering
- `mcp__council__set_model` - Change the active model

### Using Model Override

All tools support an optional `model` parameter to override the default model:

```python
# Use a specific model for a code review
mcp__council__code_review(
    code="def hello(): print('world')",
    focus="security",
    model="anthropic/claude-3-opus"  # Override default model
)

# Ask a specific model
mcp__council__ask(
    question="Explain quantum computing",
    model="google/gemini-3-pro-preview"
)
```

## Development Workflow

### 1. Making Changes
1. Edit files in `src/council/`
2. Add tests in `tests/`
3. Test locally with pytest: `pytest tests/ -v`

### 2. Deploying Changes
```bash
# Install or update (smart script that handles both)
./scripts/install.sh

# Development symlink (for rapid iteration)
./scripts/dev-link.sh
```

### 3. Testing Changes
1. After deploying, restart Claude Desktop/Code
2. Test with: `mcp__council__server_info`
3. Verify the server is running and models are available
4. Test each tool to ensure functionality

## Code Architecture

### Directory Structure
```
src/council/
├── main.py              # CouncilMCPServer (entry point)
├── manager.py           # ModelManager (OpenRouter-based)
├── json_rpc.py          # JSON-RPC 2.0 implementation
├── providers/
│   ├── base.py          # LLMProvider interface
│   └── openrouter.py    # OpenRouter implementation
├── discovery/
│   ├── model_cache.py   # TTL-based model caching
│   └── model_filter.py  # Filter by provider, capability, etc.
├── tools/
│   ├── base.py          # MCPTool base class
│   ├── ask.py           # General questions
│   ├── code_review.py   # Code review
│   ├── brainstorm.py    # Brainstorming
│   ├── test_cases.py    # Test generation
│   ├── explain.py       # Explanations
│   ├── synthesize.py    # Perspective synthesis
│   ├── list_models.py   # Model listing
│   ├── set_model.py     # Model switching
│   └── server_info.py   # Server status
├── core/
│   ├── registry.py      # Tool discovery
│   └── orchestrator.py  # Tool execution
├── services/
│   ├── cache.py         # Response caching
│   └── memory.py        # Conversation memory
└── models/              # Legacy Gemini support
```

### Core Components

1. **ModelManager** (`src/council/manager.py`)
   - Routes requests to OpenRouter API
   - Manages active model selection
   - Handles model override per-request

2. **OpenRouterProvider** (`src/council/providers/openrouter.py`)
   - OpenAI-compatible API client
   - Model listing and discovery
   - Error handling and retries

3. **CouncilMCPServer** (`src/council/main.py`)
   - Implements MCP protocol
   - Routes tool calls to appropriate handlers
   - Manages server lifecycle

### Adding New Tools

Create a new file in `src/council/tools/`:

```python
from .base import MCPTool, ToolOutput

class MyNewTool(MCPTool):
    @property
    def name(self) -> str:
        return "my_new_tool"

    @property
    def description(self) -> str:
        return "Description of what this tool does"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."},
                "model": {
                    "type": "string",
                    "description": "Optional model override"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, parameters: dict) -> ToolOutput:
        # Get model manager
        from .. import _server_instance
        model_manager = _server_instance.model_manager

        # Generate content
        prompt = f"Your prompt: {parameters['param1']}"
        model_override = parameters.get("model")
        response, model_used = model_manager.generate_content(
            prompt, model=model_override
        )

        return ToolOutput(success=True, result=response)
```

Then export it in `src/council/tools/__init__.py`.

## Configuration

### Environment Variables
```bash
# Required
OPENROUTER_API_KEY=sk-or-...

# Optional
COUNCIL_DEFAULT_MODEL=google/gemini-3-pro-preview  # Default model
COUNCIL_CACHE_TTL=3600                              # Model cache TTL (1 hour)
COUNCIL_TIMEOUT=600000                              # Request timeout (10 min)
COUNCIL_DEBUG=1                                     # Enable debug logging
```

### Model Selection
1. Default model: `google/gemini-3-pro-preview`
2. Can be changed with `set_model` tool
3. Can be overridden per-request with `model` parameter

## Testing Guidelines

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=council --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_council/test_manager.py -v
```

### Test Structure
- `tests/unit/test_council/` - Unit tests for new Council components
- `tests/unit/` - Unit tests for shared components
- `tests/integration/` - Integration tests

## Debugging Tips

### Check Server Status
```bash
# From Claude
mcp__council__server_info

# Check logs
tail -f ~/.claude-mcp-servers/council/logs/council-mcp-server.log
```

### Common Issues
1. **"No API Key"** - Set OPENROUTER_API_KEY in .env
2. **Model not available** - Check model ID with list_models
3. **Timeout errors** - Increase COUNCIL_TIMEOUT
4. **Rate limits** - OpenRouter has per-model rate limits

## Quick Command Reference

```bash
# Development
./scripts/install.sh         # Deploy to MCP location
./scripts/dev-link.sh        # Create development symlink
pytest tests/ -v             # Run tests
python scripts/bundler.py    # Create single-file bundle

# Testing MCP Tools (from Claude)
mcp__council__server_info          # Check status
mcp__council__ask                  # General query
mcp__council__code_review          # Review code
mcp__council__brainstorm           # Generate ideas
mcp__council__test_cases           # Create tests
mcp__council__explain              # Get explanation
mcp__council__list_models          # List available models
mcp__council__set_model            # Change active model

# Configuration
cp .env.example .env         # Create config
vim .env                     # Add OPENROUTER_API_KEY
```

## Version History

- **v4.0.0**: Council - Multi-model support via OpenRouter
- **v3.0.0**: Modular architecture with bundler
- **v2.0.0**: Dual-model support with fallback
- **v1.0.0**: Initial Gemini integration

## Important Notes

1. **Multi-model collaboration** - Use different models for different tasks
2. **Model override** - All tools support optional `model` parameter
3. **OpenRouter pricing** - Some models are free, others are paid
4. **Updates require restart** - Restart Claude Desktop/Code after changes

Remember: Council enhances Claude's capabilities through collaboration with any AI model. Use the right model for each task!
