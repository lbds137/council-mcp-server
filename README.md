# Gemini MCP Server

A Model Context Protocol (MCP) server that enables Claude to collaborate with Google's Gemini AI models.

## Features

- 🤖 **Multiple Gemini Tools**: Ask questions, review code, brainstorm ideas, generate tests, and get explanations
- 🔄 **Dual-Model Support**: Automatic fallback from experimental to stable models
- ⚡ **Configurable Models**: Easy switching between different Gemini variants
- 🛡️ **Reliable**: Never lose functionality with automatic model fallback
- 📊 **Transparent**: Shows which model was used for each response

## Quick Start

### 1. Prerequisites

- Python 3.9+
- [Claude Desktop](https://claude.ai/download)
- [Google AI API Key](https://makersuite.google.com/app/apikey)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/lbds137/gemini-mcp-server.git
cd gemini-mcp-server

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 3. Configuration

Edit `.env` to configure your models:

```bash
# Your Gemini API key (required)
GEMINI_API_KEY=your_api_key_here

# Model configuration (optional - defaults shown)
GEMINI_MODEL_PRIMARY=gemini-2.5-pro-preview-06-05
GEMINI_MODEL_FALLBACK=gemini-1.5-pro
GEMINI_MODEL_TIMEOUT=10000
```

### 4. Development Setup

For development with PyCharm or other IDEs:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Run tests
python -m pytest
```

### 5. Register with Claude

```bash
# Install to MCP location
./scripts/install.sh

# Or manually register
claude mcp add gemini-collab python3 ~/.claude-mcp-servers/gemini-collab/server.py
```

## Available Tools

### `ask_gemini`
General questions and problem-solving assistance.

### `gemini_code_review`
Get code review feedback focusing on security, performance, and best practices.

### `gemini_brainstorm`
Collaborative brainstorming for architecture and design decisions.

### `gemini_test_cases`
Generate comprehensive test scenarios for your code.

### `gemini_explain`
Get clear explanations of complex code or concepts.

### `server_info`
Check server status and model configuration.

## Model Configurations

### Best Quality (Default)
```bash
GEMINI_MODEL_PRIMARY=gemini-2.5-pro-preview-06-05
GEMINI_MODEL_FALLBACK=gemini-1.5-pro
```

### Best Performance
```bash
GEMINI_MODEL_PRIMARY=gemini-2.5-flash-preview-05-20
GEMINI_MODEL_FALLBACK=gemini-2.0-flash
```

### Most Cost-Effective
```bash
GEMINI_MODEL_PRIMARY=gemini-2.0-flash
GEMINI_MODEL_FALLBACK=gemini-2.0-flash-lite
```

## Development

### Project Structure
```
gemini-mcp-server/
├── src/
│   └── gemini_mcp/
│       ├── __init__.py
│       └── server.py      # Main server with DualModelManager
├── tests/
│   └── test_server.py
├── scripts/
│   ├── install.sh       # Quick installation script
│   ├── update.sh        # Update deployment script
│   └── dev-link.sh      # Development symlink script
├── docs/
│   └── BUILD_YOUR_OWN_MCP_SERVER.md
├── .claude/
│   └── settings.json    # Claude Code permissions
├── .env                 # Your configuration (git-ignored)
├── .env.example         # Example configuration
├── .gitignore
├── CLAUDE.md           # Instructions for Claude Code
├── LICENSE
├── README.md           # This file
├── docs/
│   ├── BUILD_YOUR_OWN_MCP_SERVER.md
│   ├── DUAL_MODEL_CONFIGURATION.md # Dual-model setup guide
│   ├── PYCHARM_SETUP.md
│   └── TESTING.md
├── requirements.txt
├── setup.py
├── package.json        # MCP registration metadata
└── package-lock.json
```

### Running Tests
```bash
python -m pytest tests/ -v
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Updating

To update your local MCP installation after making changes:

```bash
./scripts/update.sh
```

This will copy the latest version to your MCP servers directory.

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
echo $GEMINI_API_KEY

# Test directly
python -c "import google.generativeai as genai; genai.configure(api_key='$GEMINI_API_KEY'); print('✅ API key works')"
```

### Model Availability
Some models may not be available in all regions. Check the fallback model in logs if primary fails consistently.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Claude](https://claude.ai) using the Model Context Protocol
- Powered by [Google's Gemini AI](https://deepmind.google/technologies/gemini/)
