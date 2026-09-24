# Council MCP Server

A Model Context Protocol (MCP) server that enables Claude to collaborate with multiple AI models via OpenRouter. Access OpenAI, Google, DeepSeek, Moonshot (Kimi), Z.ai (GLM), Qwen, xAI, Mistral and many more.

## Features

- **Multi-Model Support**: Access hundreds of models via OpenRouter, plus GLM on a Z.ai coding plan
- **Dynamic Model Discovery**: List and filter available models by provider, capability, or pricing
- **Per-Request Model Override**: Use different models for different tasks
- **Multiple Collaboration Tools**: Multi-model debates, code review, debugging, refactoring, brainstorming, test generation, explanations, multi-turn conversations
- **Response Caching**: A repeated question to the same model is answered from cache for an hour

## Quick Start

### 1. Prerequisites

- Python 3.12+
- [Claude Desktop](https://claude.ai/download) or [Claude Code](https://claude.ai/code)
- [OpenRouter API Key](https://openrouter.ai/keys)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/lbds137/council-mcp-server.git
cd council-mcp-server

# Create the dev venv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 3. Configuration

**API keys** are best stored encrypted, so they never sit in a plaintext file.
On a Linux machine with systemd 256 or newer, run:

```bash
# Prompts for the key with input hidden, or reads it from a pipe
./scripts/set-secret.sh OPENROUTER_API_KEY

# Optional: route GLM models through a Z.ai coding plan (flat rate)
./scripts/set-secret.sh ZAI_CODING_API_KEY
```

The keys live together in one encrypted file,
`~/.claude-mcp-servers/council/credentials/keys.cred`, which only your user on
that machine can decrypt. Running `set-secret.sh` again for a name replaces that
key and keeps the others. Council decrypts the file once at startup.
A key set as an environment variable before council starts takes priority over
a stored credential; a stored credential takes priority over a `.env` line, so
a stale `.env` can't shadow a new key. To keep the credentials somewhere else,
set `COUNCIL_CREDENTIALS_DIR` in the server's environment (for example in the
MCP server entry of your Claude config). It is read before `.env` loads, so a
`.env` line for it has no effect.

**Other settings** go in `.env` (optional; defaults shown):

```bash
COUNCIL_DEFAULT_MODEL=~openai/gpt-sol-latest
COUNCIL_CACHE_TTL=3600
COUNCIL_TIMEOUT=600000
```

With a Z.ai key set, requests for GLM models the plan carries (`~z-ai/glm-latest`,
`z-ai/glm-5.3`, or a bare `glm-5.3`) go to the plan. The output names the route,
for example `[Model: z-ai/glm-5.3 · Z.ai plan]`. If the plan fails (quota, busy,
outage), council retries once through OpenRouter and says so in the same place.

### 4. Register with Claude

```bash
# Install to MCP location
./scripts/install.sh

# Or manually register (use the venv's python, not the system python3)
claude mcp add council -s user -- ~/.claude-mcp-servers/council/.venv/bin/python ~/.claude-mcp-servers/council/launcher.py
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
| `debate` | 2-4 models argue a topic, rebut each other, and one synthesizes (default panel: GPT, GLM, Kimi) |
| `debug` | Diagnose an error from its message, stack trace and code |
| `refactor` | Suggest refactorings toward a stated goal |

### Conversations

| Tool | Description |
|------|-------------|
| `start_conversation` | Open a multi-turn conversation with a model |
| `continue_conversation` | Send the next message in a conversation |
| `get_conversation_history` | Show a conversation's turns |
| `list_conversations` | List open conversations |
| `end_conversation` | Close a conversation |

### Model Management

| Tool | Description |
|------|-------------|
| `server_info` | Check server status and current model |
| `list_models` | List available models with filtering |
| `set_model` | Change the active model for subsequent requests |
| `recommend_model` | Suggest models for a task (coding, reasoning, vision, ...) |

### Model Override

All tools support an optional `model` parameter to use a specific model:

```python
# Use Kimi for code review
mcp__council__code_review(
    code="def hello(): print('world')", focus="security", model="~moonshotai/kimi-latest"
)

# Use GLM for brainstorming
mcp__council__brainstorm(topic="API design patterns", model="~z-ai/glm-latest")
```

## Popular Model Configurations

IDs that start with `~` are OpenRouter aliases that always point at the newest
model in a family, so they don't go stale. Council's recommendations leave out
Anthropic models on purpose: Claude Code can already run its own Claude agents,
so council is for other model families.

### OpenAI GPT (Default)
```bash
COUNCIL_DEFAULT_MODEL=~openai/gpt-sol-latest
```

### Moonshot Kimi
```bash
COUNCIL_DEFAULT_MODEL=~moonshotai/kimi-latest
```

### Z.ai GLM
```bash
COUNCIL_DEFAULT_MODEL=~z-ai/glm-latest
```

### DeepSeek
```bash
COUNCIL_DEFAULT_MODEL=~deepseek/deepseek-pro-latest
```

### Google Gemini
```bash
COUNCIL_DEFAULT_MODEL=~google/gemini-pro-latest
```

### Qwen (Free)
```bash
COUNCIL_DEFAULT_MODEL=qwen/qwen3.8-27b:free
```

## Development

### Project Structure
```
council-mcp-server/
├── src/council/           # Main source code
│   ├── main.py           # CouncilMCPServer entry point
│   ├── manager.py        # ModelManager (routes to OpenRouter or the Z.ai plan)
│   ├── credentials.py    # Decrypts stored API keys at startup
│   ├── providers/        # OpenRouter and Z.ai coding-plan providers
│   ├── discovery/        # Model registry, filtering and caching
│   ├── tools/            # MCP tool implementations
│   ├── core/             # Tool registry and orchestrator
│   └── services/         # Response cache and conversation sessions
├── tests/                # Test suite
├── scripts/              # install.sh, set-secret.sh, check_models.py
├── launcher.py           # Entry point the installed server runs
├── CLAUDE.md            # Claude Code instructions
└── README.md            # This file
```

### Running Tests
```bash
# Uses the repo's .venv (see Installation)
make test        # or: .venv/bin/python -m pytest tests/
make test-cov    # with coverage
```

## Updating

To update your local MCP installation after making changes:

```bash
./scripts/install.sh
```

The script installs the `council` package, as of the commit you have checked
out, into the server's own venv (`~/.claude-mcp-servers/council/.venv`), next to
`launcher.py`, and writes that commit to `INSTALLED` there. It installs from git,
so uncommitted changes are left out (the script warns about them): commit first.
The install is a snapshot: switching branches in the repo doesn't change the
running server. To roll back,
check out the earlier commit and run `./scripts/install.sh` again.

Then reconnect the server in each open Claude Code session (`/mcp` → council →
Reconnect), or restart Claude Desktop.

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
# Check the stored credentials exist (this never prints a key)
ls ~/.claude-mcp-servers/council/credentials/

# Store or replace a key
./scripts/set-secret.sh OPENROUTER_API_KEY
```
Then reconnect council and run `mcp__council__server_info` or
`mcp__council__list_models(limit=5)`. The server log is
`~/.claude-mcp-servers/council/logs/council-mcp-server.log`.

### Model Not Available
Use `list_models` to find available models:
```python
mcp__council__list_models(provider="moonshotai")
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
