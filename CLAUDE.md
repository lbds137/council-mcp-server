# CLAUDE.md - Council MCP Server

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@~/.claude/CLAUDE.md

## Project Overview

**Council** is a Model Context Protocol (MCP) server that enables Claude to collaborate with multiple AI models via OpenRouter. It provides a provider-agnostic way for AI-to-AI collaboration on complex tasks, with access to GPT, Gemini, DeepSeek, Kimi, GLM, Qwen and many other models.

### Key Features
- **Multi-Model Support**: Hundreds of models via OpenRouter, plus GLM on the Z.ai coding plan
- **Dynamic Model Discovery**: List and filter available models by provider, capability, or pricing
- **Per-Request Model Override**: Use different models for different tasks
- **Multiple Collaboration Tools**: Code review, debugging, refactoring, brainstorming, test generation, explanations, multi-turn conversations
- **Response Caching**: Tools whose answer depends only on their input opt in (`is_cacheable`); the key includes the model

## Available MCP Tools

Since this MCP server is already running, you can use these tools directly:

### Core Tools
- `mcp__council__ask` - Ask any model general questions
- `mcp__council__code_review` - Get code review
- `mcp__council__brainstorm` - Brainstorm ideas with AI
- `mcp__council__test_cases` - Generate test cases
- `mcp__council__explain` - Get explanations
- `mcp__council__synthesize_perspectives` - Combine multiple viewpoints
- `mcp__council__debate` - 2-4 models debate a topic (openings, rebuttals, synthesis); calls run in parallel, one per debater per round
- `mcp__council__debug` - Diagnose an error
- `mcp__council__refactor` - Suggest refactorings

### Conversations
- `mcp__council__start_conversation` / `continue_conversation` - Multi-turn conversation with a model
- `mcp__council__get_conversation_history` / `list_conversations` / `end_conversation`

### Model Management
- `mcp__council__server_info` - Check server status and current model
- `mcp__council__list_models` - List available models with filtering
- `mcp__council__set_model` - Change the active model
- `mcp__council__recommend_model` - Suggest models for a task

### Using Model Override

All tools support an optional `model` parameter to override the default model:

```python
# Use a specific model for a code review
mcp__council__code_review(
    code="def hello(): print('world')",
    focus="security",
    model="~moonshotai/kimi-latest",  # Override default model
)

# Ask a specific model
mcp__council__ask(question="Explain quantum computing", model="~z-ai/glm-latest")
```

## Development Workflow

### 1. Making Changes
1. Edit files in `src/council/`
2. Add tests in `tests/`
3. Test locally: `make test` (runs `.venv/bin/python -m pytest tests/`)

### 2. Deploying Changes
```bash
# Install or update: pip-installs the checked-out commit (from git) into
# ~/.claude-mcp-servers/council/.venv and records it in INSTALLED there
./scripts/install.sh
```
Only committed code ships: the script warns about uncommitted changes and leaves them
out, so commit (and normally merge) first. The install is a snapshot, not editable, so the
running server doesn't follow branch switches. Roll back by checking out the earlier
commit and running the script again; `~/.claude-mcp-servers/council/INSTALLED` records the
live sha and time.

### 3. Testing Changes
1. After deploying, reconnect council in each open session (`/mcp` → council → Reconnect)
2. Test with: `mcp__council__server_info`
3. Verify the server is running and models are available
4. Test each tool to ensure functionality

### 4. Shipping Changes
The owner doesn't read diffs; the pre-push hook and CI are the gates.
- **Small fixes** (docs, one-file changes): commit straight to `main`. The pre-push hook runs ruff (lint and format), mypy and pytest.
- **Bigger changes** (several files, behavior changes): make a branch and open a PR, then merge it in the same session once CI is green (`gh pr checks`, then `gh pr merge --rebase --delete-branch`). CI finishes in under a minute, so no monitor is needed. When the gates can't fully vouch for a change, run a fresh-context review agent before merging.
- The GitHub ruleset in `.github/rulesets/main.json` (active since 2026-09-24) blocks force-pushes to `main` and its deletion, with no bypass. It doesn't require CI, so direct small-fix pushes still work. Never rewrite `main`'s history.
- Implementation over ~5 lines, prose included, goes through delegation (§ 5); delegated units
  always get the fresh-context review. Delegation decides who writes the diff; the small/bigger
  split above decides how it ships, so a 20-line docs fix is delegated and then committed
  straight to `main`.

### 5. Delegation
This repo has adopted the harness `delegation` skill: the driver grounds and specs each unit,
a `harness:implementer` executes it in a worktree under `.claude/worktrees/` (gitignored), the
driver reads the full diff, runs a fresh-context review agent, transfers the patch with the
skill's block, then runs the gates from the main checkout and ships per § 4. Specs live in
`.claude/dispatch/` (gitignored). The skill's own text is the procedure; this section only
fills its project slots.
- **Worktree base.** `.claude/settings.json` sets `worktree.baseRef` to `head`, so the agent
  tree is cut from the main checkout's HEAD at spawn time: park the main checkout on the unit's
  branch at the spec's SHA before the Agent call. A driver session that is itself
  worktree-isolated (a background job) cannot reach a second worktree: there the worker edits
  the driver's tree directly, dispatched without the isolation flag, and the transfer step is
  skipped.
- **Step 0 for a bare worktree:** `python -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
  The Makefile falls back to the system `python` when there is no `.venv`, and it has no ruff,
  so without this the first gate fails for reasons unrelated to the diff. The dev extras are
  declared in `setup.py`, not `pyproject.toml`. Step 0 builds on the system Python 3.13; 3.12
  compatibility is checked only by CI.
- **The step-0 self-heal block in the delegation skill is the one sanctioned `git reset --hard`
  in this repo.**
- **Gate** (what the commit hook, the pre-push hook and CI run; copy into every spec, run one
  at a time): `make lint`, `.venv/bin/python -m ruff format --check src/ tests/ scripts/` (the
  check form; `make format` rewrites files), `make type-check`, `make test` (about 600 tests,
  about 10 s, no key or TPM needed: provider calls are patched), `make pre-commit` (the
  installed commit hook's checks over every file: trailing whitespace, final newline,
  yaml/json/toml syntax, ruff; its ruff-format hook rewrites rather than checks, so run it
  after the check form; its cached hook environments live under `~/.cache/pre-commit`).
- **Ceilings:** ruff `line-length = 100`, rules E/F/W/I/B/UP, `tests/**` exempt from E501;
  mypy checks `src/` only, with `warn_unused_ignores`, so a stale `# type: ignore` fails it.
  No file or function length caps, no coverage threshold.
- **Landmines:** tool discovery (`src/council/core/registry.py`) imports every `tools/*.py`
  file except `base.py` and `_`-prefixed ones, and registers each concrete `MCPTool` subclass
  defined there, so a second concrete subclass in a tool file (a shared base that implements
  every abstract member, a copy left behind) becomes a live tool; plain helper classes are
  fine. `is_cacheable` must stay False for any tool that reads or changes server state.
- **Local-only list** (the driver keeps these; never in a spec): the TPM-sealed keys under
  `~/.claude-mcp-servers/council/credentials`, the installed server and `scripts/install.sh`
  (an install is machine-wide), and anything that calls OpenRouter or Z.ai live (the
  `mcp__council__*` tools, `make check-models`).
- **Not adopted yet:** cloud units (no cloud step-0 script exists; units run locally until one
  is written, starting from the local step 0 on a 3.12 or 3.13 toolchain, no secrets needed)
  and the `dispatch-posture-gate` hook (`HARNESS_DISPATCH_SRC_RE` unset; enable it if inline
  edits keep slipping past the ~5-line rule).

## Code Architecture

### Directory Structure
```
src/council/
├── main.py              # CouncilMCPServer (entry point)
├── manager.py           # ModelManager: routes GLM to the Z.ai plan, the rest to OpenRouter
├── credentials.py       # Decrypts systemd user credentials into the environment
├── json_rpc.py          # JSON-RPC 2.0 implementation
├── providers/
│   ├── base.py          # LLMProvider interface and error classes
│   ├── openrouter.py    # OpenRouter implementation
│   └── zai.py           # Z.ai coding-plan implementation
├── discovery/
│   ├── model_registry.py  # Curated models and task recommendations
│   ├── model_cache.py   # TTL-based model caching
│   └── model_filter.py  # Filter by provider, capability, etc.
├── tools/
│   ├── base.py          # MCPTool base class, ToolOutput
│   ├── ask.py, code_review.py, brainstorm.py, test_cases.py, explain.py,
│   ├── synthesize.py, debug.py, refactor.py   # Answer tools (cacheable)
│   ├── debate.py        # Multi-model debate
│   ├── conversation.py  # Multi-turn conversation tools
│   ├── list_models.py, set_model.py, recommend_model.py, server_info.py
├── core/
│   ├── registry.py      # Tool discovery (concrete MCPTool subclasses)
│   └── orchestrator.py  # Tool execution, response cache, execution counts
└── services/
    ├── cache.py         # Response cache (LRU + TTL)
    └── session_manager.py  # Conversation sessions
```

### Core Components

1. **ModelManager** (`src/council/manager.py`)
   - Routes GLM requests the Z.ai plan carries to the plan (one OpenRouter retry on failure), everything else to OpenRouter
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
from .base import MCPTool, ToolOutput, get_model_manager


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
                "model": {"type": "string", "description": "Optional model override"},
            },
            "required": ["param1"],
        }

    async def execute(self, parameters: dict) -> ToolOutput:
        model_manager = get_model_manager()
        if not model_manager:
            return ToolOutput(success=False, error="Model manager not available")

        # Generate content
        prompt = f"Your prompt: {parameters['param1']}"
        model_override = parameters.get("model")
        response, model_used = model_manager.generate_content(prompt, model=model_override)

        return ToolOutput(success=True, result=response)
```

Then export it in `src/council/tools/__init__.py` for the package API; discovery
(`src/council/core/registry.py`) finds it by file, not by that export.

If the tool's answer depends only on its input and the model, override `is_cacheable(parameters)` to return True so repeated calls are served from cache. Never do this for a tool that reads or changes server state.

A tool that makes several model calls can call `report_progress(done, total, message)` (from `.base`) after each one; the client then shows how far it has got. It does nothing when the client didn't ask for progress.

## Configuration

### API Keys
Keys are stored as encrypted systemd user credentials, not in `.env`:
`scripts/set-secret.sh NAME` adds or replaces NAME in `~/.claude-mcp-servers/council/credentials/keys.cred`
(one credential holding every key as NAME=value lines; host key + TPM2, not bound to firmware
state), and `src/council/credentials.py` decrypts it at startup. One file means one TPM decrypt
(about 3 s; the TPM serializes them, so separate files would cost 3 s each). Older per-key
`NAME.cred` files still load for names keys.cred lacks, and cost nothing otherwise. An environment variable set before startup beats a credential; a credential
beats a `.env` line.
Never print a key. Pipe it straight into `set-secret.sh` instead.
- `OPENROUTER_API_KEY` (required)
- `ZAI_CODING_API_KEY` (optional): GLM models the Z.ai coding plan carries are routed
  there (`src/council/providers/zai.py`), with one OpenRouter retry on failure. On this
  Deck it comes from Tzurot's Railway dev env:
  `railway variables --environment development --service ai-worker --json | jq -er .ZAI_CODING_API_KEY | ~/Projects/council-mcp-server/scripts/set-secret.sh ZAI_CODING_API_KEY`
  (run from `~/Projects/tzurot`, which Railway is linked to; `jq -e` fails instead of storing "null").

### Environment Variables
```bash
# Optional
COUNCIL_DEFAULT_MODEL=~openai/gpt-sol-latest       # Default model
COUNCIL_CACHE_TTL=3600                              # Model cache TTL (1 hour)
COUNCIL_TIMEOUT=600000                              # Request timeout (10 min)
COUNCIL_DEBUG=1                                     # Enable debug logging
```

### Model Selection
1. Default model: `~openai/gpt-sol-latest` (a `~` ID is an OpenRouter alias for a family's newest model)
2. Can be changed with `set_model` tool
3. Can be overridden per-request with `model` parameter
4. Recommendations (`recommend_model`, the `server_info` guide) come from
   `src/council/discovery/model_registry.py`. It leaves out Anthropic models on purpose:
   Claude Code can spawn its own Claude agents, so council is for other families.
   `make check-models` lists registry IDs that OpenRouter has dropped.
   When refreshing the registry, rank OpenAI, Google, DeepSeek, Kimi, GLM, Qwen, MiniMax, xAI and Mistral, and give the Chinese open-weight families (GLM, Kimi, Qwen, DeepSeek, MiniMax) full entries, not free-tier footnotes: the owner leans on them across her projects. Never propose a Claude default; `test_no_anthropic_models` enforces the exclusion, and an explicit `model="~anthropic/..."` override still works. Prefer OpenRouter's floating `~vendor/family-latest` aliases so entries don't go stale. The default stays `~openai/gpt-sol-latest` by the owner's choice; GLM on the Z.ai plan is close to free (her plan use peaks around 60% a week).

## Testing Guidelines

### Running Tests
```bash
# Run all tests
.venv/bin/python -m pytest tests/ -v

# Run with coverage
.venv/bin/python -m pytest tests/ --cov=council --cov-report=term-missing

# Run specific test file
.venv/bin/python -m pytest tests/unit/test_council/test_manager.py -v
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
1. **"No API Key"** - Store it: `scripts/set-secret.sh OPENROUTER_API_KEY`, then reconnect
2. **Model not available** - Check model ID with list_models
3. **Timeout errors** - Increase COUNCIL_TIMEOUT
4. **Rate limits** - OpenRouter has per-model rate limits
5. **Council starts without keys** - Check `$XDG_RUNTIME_DIR/council/tpm-stalled`. Decrypts take turns through the lock `$XDG_RUNTIME_DIR/council/decrypt.lock` (15 s wait, then the server starts without keys). A timed-out decrypt writes `tpm-stalled`, and startups then skip the TPM for 5 minutes; a reboot clears it. Cause seen 2026-09-24: parallel headless `claude -p` workers each started council and wedged the TPM queue (16+ D-state kworkers). Headless `claude -p` calls must pass `--strict-mcp-config` so they load no MCP servers.
6. **Stale server in a long-lived session** - If `server_info` shows a default model other than `COUNCIL_DEFAULT_MODEL` in the installed `.env` (e.g. `anthropic/claude-opus-4.6`), the process predates the current install. Its GLM calls then go through billed OpenRouter (the `[Model: …]` label lacks `· Z.ai plan`). Pass `model:` explicitly, or reconnect (`/mcp` → council → Reconnect).
7. **Old server process after a reconnect** - Claude Code keeps the replaced server process alive, idle, until the session exits. Stopping it by PID with `kill -TERM <pid>` is safe; council keeps working (tested 2026-09-23). List first and kill by PID, never by pattern.
8. **Context windows** - OpenRouter's headline `context_length` is the largest window ANY provider serves (GLM-5.3 shows 1.31M because of Cloudflare; Z.ai and most hosts serve 1M). Read real per-provider windows from `/api/v1/models/<id>/endpoints`. Registry `context_window` is the median across providers.

## Quick Command Reference

```bash
# Development
./scripts/install.sh         # Deploy to MCP location
make test                    # Run tests (repo .venv)
make check-models            # Find registry model IDs OpenRouter dropped

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
scripts/set-secret.sh OPENROUTER_API_KEY   # Store the key (encrypted)
vim ~/.claude-mcp-servers/council/.env     # Optional settings (default model, TTL, timeout)
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
4. **Updates require a reconnect** - Run `scripts/install.sh`, then `/mcp` → council → Reconnect

Remember: Council enhances Claude's capabilities through collaboration with any AI model. Use the right model for each task!
