# Council MCP Server

A Model Context Protocol (MCP) server that enables Claude to collaborate with multiple AI models via OpenRouter. Access 100+ models from Google, Anthropic, OpenAI, Meta, Mistral, and more.

## Features

- **Multi-Model Support**: Access 100+ models via OpenRouter (Gemini, GPT, Claude, Llama, Mistral, etc.)
- **Dynamic Model Discovery**: List and filter available models by provider, capability, or pricing
- **Per-Request Model Override**: Use different models for different tasks
- **Multiple Collaboration Tools**: Code review, brainstorming, test generation, explanations
- **Response Caching**: Automatic caching for repeated queries

## Quick Start

### 1. Prerequisites

- Python 3.9+
- [Claude Desktop](https://claude.ai/download) or [Claude Code](https://claude.ai/code)
- [OpenRouter API Key](https://openrouter.ai/keys)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/lbds137/gemini-mcp-server.git
cd gemini-mcp-server

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### 3. Configuration

Edit `.env` to configure:

```bash
# Your OpenRouter API key (required)
OPENROUTER_API_KEY=sk-or-...

# Model configuration (optional - defaults shown)
COUNCIL_DEFAULT_MODEL=google/gemini-3-pro-preview
COUNCIL_CACHE_TTL=3600
COUNCIL_TIMEOUT=600000
```

### 4. Register with Claude

```bash
# Install to MCP location
./scripts/install.sh

# Or manually register
claude mcp add council python3 ~/.claude-mcp-servers/council/launcher.py
```

## Available Tools

### Core Tools

| Tool | Description |
|------|-------------|
| `ask` | General questions and problem-solving assistance |
| `code_review` | Code review feedback (security, performance, best practices) |
| `brainstorm` | Collaborative brainstorming for architecture and design |
| `test_cases` | Generate comprehensive test scenarios |
| `explain` | Clear explanations of complex code or concepts |
| `synthesize_perspectives` | Combine multiple viewpoints into a coherent summary |

### Model Management

| Tool | Description |
|------|-------------|
| `server_info` | Check server status and current model |
| `list_models` | List available models with filtering |
| `set_model` | Change the active model for subsequent requests |

### Model Override

All tools support an optional `model` parameter to use a specific model:

```python
# Use Claude for code review
mcp__council__code_review(
    code="def hello(): print('world')",
    focus="security",
    model="anthropic/claude-3-opus"
)

# Use GPT-4 for brainstorming
mcp__council__brainstorm(
    topic="API design patterns",
    model="openai/gpt-4-turbo"
)
```

## Popular Model Configurations

### Google Gemini (Default)
```bash
COUNCIL_DEFAULT_MODEL=google/gemini-3-pro-preview
```

### Anthropic Claude
```bash
COUNCIL_DEFAULT_MODEL=anthropic/claude-3.5-sonnet
```

### OpenAI GPT-4
```bash
COUNCIL_DEFAULT_MODEL=openai/gpt-4-turbo
```

### Meta Llama (Free)
```bash
COUNCIL_DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

## Development

### Project Structure
```
gemini-mcp-server/
├── src/council/           # Main source code
│   ├── main.py           # CouncilMCPServer entry point
│   ├── manager.py        # ModelManager (OpenRouter)
│   ├── providers/        # LLM provider implementations
│   ├── discovery/        # Model discovery and filtering
│   ├── tools/            # MCP tool implementations
│   ├── core/             # Registry and orchestrator
│   └── services/         # Cache and memory
├── tests/                # Test suite
├── scripts/              # Installation scripts
├── server.py             # Bundled single-file server
├── launcher.py           # Launcher with venv support
├── CLAUDE.md            # Claude Code instructions
└── README.md            # This file
```

### Running Tests
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v
```

### Building the Bundle
```bash
# Generate single-file server.py
python scripts/bundler.py

# Deploy to MCP location
./scripts/install.sh
```

## Updating

To update your local MCP installation after making changes:

```bash
./scripts/install.sh
```

Then restart Claude Desktop/Code.

## Troubleshooting

### Server not found
```bash
# Check registration
claude mcp list

# Re-register if needed
./scripts/install.sh
```

### API Key Issues
```bash
# Verify environment variable
echo $OPENROUTER_API_KEY

# Test with list_models tool
mcp__council__list_models(limit=5)
```

### Model Not Available
Use `list_models` to find available models:
```python
mcp__council__list_models(provider="google")
```

## Version History

- **v4.0.0**: Council - Multi-model support via OpenRouter
- **v3.0.0**: Modular architecture with bundler
- **v2.0.0**: Dual-model support with fallback
- **v1.0.0**: Initial Gemini integration

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Claude](https://claude.ai) using the Model Context Protocol
- Powered by [OpenRouter](https://openrouter.ai/) for multi-model access
