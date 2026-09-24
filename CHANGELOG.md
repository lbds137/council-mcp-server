# Changelog

All notable changes to the Council MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `recommend_model` honours `prefer_fast` (flash-class models rated for the task first, best rating first) and `min_context` (drops models whose window is too small and names them). Each registry entry records the window most providers serve, and each recommendation shows it; `make check-models` reports windows that have drifted
- `debate` tool: 2-4 models give opening statements (assigned stances or their own views), rebut each other, and a synthesis model weighs the result. Each round's calls run in parallel; a debater that fails is noted and sits out, and a debate missing a voice isn't cached
- GLM models the Z.ai coding plan carries are routed to the plan when `ZAI_CODING_API_KEY` is set (`~z-ai/*` aliases resolve against Z.ai's own model list), with one OpenRouter retry on failure; the output names the route
- API keys can be stored as encrypted systemd user credentials (`scripts/set-secret.sh`), decrypted at startup, instead of plaintext in `.env`
- `scripts/check_models.py` (`make check-models`) lists registry model IDs that OpenRouter no longer serves
- Comprehensive test coverage for JSON-RPC layer (30 tests)
- Complete test suite for main.py entry point (16 tests)
- Test suite for BrainstormTool (12 tests)
- Python path setup in conftest.py for proper test imports
- python-dotenv to install_requires
- Type annotations throughout the codebase

### Changed
- `scripts/install.sh` installs the `council` package, as of the checked-out commit and straight from git, into the server venv instead of copying a generated single-file bundle; uncommitted changes don't ship; `launcher.py` just runs `council.main`. The deployed server is the code the tests run. The install writes the deployed commit to `INSTALLED`; roll back by reinstalling an earlier commit. The bundler (`scripts/bundler.py`), the committed `server.py`, and `requirements.txt` (a duplicate of `setup.py`'s dependencies) are gone
- `test_cases` sends code and feature descriptions with one neutral prompt instead of guessing which it got by keywords (it read "Users can classify tickets" as code)
- `debate` rejects more explicit models than positions, instead of silently leaving the extra models out; `recommend_model`'s "left out" note names only models that would otherwise have been listed
- All API keys live in one encrypted credential, `keys.cred`, so startup needs one TPM decrypt (about 3.5 s instead of about 7 s with two keys). `set-secret.sh NAME` adds or replaces one key in it; older per-key `NAME.cred` files still load for names it lacks
- Linting and formatting moved from flake8, black and isort to ruff, which also runs bugbear and pyupgrade rules; annotations use the Python 3.12 forms (`dict[...]`, `X | None`), and the two `str, Enum` classes are `StrEnum`
- Model registry refreshed to September 2026 and keyed on OpenRouter's floating `~vendor/family-latest` aliases, so new releases are picked up without edits
- Anthropic models removed from the registry and all recommendations: Claude Code can spawn its own Claude agents, so council covers other families. Recommendations draw on OpenAI, Google, DeepSeek, Kimi, GLM and Qwen; xAI, MiniMax and Mistral are rated for `list_models`
- Default model is now `~openai/gpt-sol-latest` (GPT-6 Sol)
- `server_info`'s quick guide is generated from the registry instead of a hand-written copy
- `recommend_model` prints full model IDs, which is what the `model` parameter accepts
- Test coverage increased from 49% to 80%, and every tool now has its own tests

### Removed
- The Gemini-era debate protocol (it called a tool that no longer existed and nothing could reach it)
- `ConversationMemory` and its models: nothing wrote to it, so `server_info` always showed zero turns. `server_info` now reports the number of open conversations instead
- The `BaseTool` compatibility class, the `GeminiMCPServer` alias, and the unused `council_manager` lookups in `list_models` and `set_model`
- Stale Gemini-era files: `TEST_STATUS.md`, `TEST_COVERAGE_REPORT.md`, `test_runner.sh`, `run_tests.py`, and `docs/` pages for v3 migration, PyCharm, troubleshooting and old review suggestions

### Fixed
- `set_model` with `"model": null` crashed instead of asking for a model ID
- `synthesize_perspectives` failed with a bare `'content'` error when a perspective had no content, and labelled a perspective with an empty source `**:**`
- The response cache served stale results: every tool was cached for an hour keyed on its arguments alone, so `set_model` could report a switch that didn't happen, a question after a model switch got the old model's answer, and a repeated conversation message never reached the model. Only tools whose answer depends on their input alone are cached now, and the key names the model
- Tool discovery from source registered no tools (it looked for `BaseTool` subclasses; the tools subclass `MCPTool`). Only the bundle worked, through its own discovery
- A failed conversation reply left the unanswered message in the session, so a retry sent it twice
- OpenRouter's model list never refreshed, and a failed fetch looked like an empty catalog; it now refreshes per `COUNCIL_CACHE_TTL`, and a failed first fetch is reported as an error
- OpenRouter errors are classified by HTTP status, and the SDK's "Request timed out." counts as retryable
- The orchestrator kept every tool result in memory for the life of the process; it keeps counters now
- The bundler no longer regex-rewrites the orchestrator; the bundle runs the source orchestrator as written
- Fallback default model `google/gemini-3-pro-preview` no longer exists on OpenRouter
- `list_models` provider filter missed `~` alias entries (their provider read as `~openai`)
- Responses name the model OpenRouter actually served, not the `~` alias that was requested
- Model metadata lookup no longer gives an older model a newer model's entry when its ID is a prefix of the newer key
- Release workflow built on Python 3.11, below `python_requires>=3.12`; it now uses 3.13
- All mypy type errors resolved - project now passes strict type checking
- Test import errors in CI (ModuleNotFoundError issues)
- Optional type hints in JSON-RPC classes
- ToolOutput import conflicts between models.base and tools.base
- CI dependency issues - all tests now pass in CI
- Model manager access pattern for tools in bundled mode

## [2.0.0] - 2025-06-10

### Added
- Dual-model support with automatic fallback
- DualModelManager class for handling primary and fallback models
- Configurable timeout for model responses
- Environment variable support for model configuration
- Comprehensive error handling and logging
- Model usage indicators in responses

### Changed
- Complete rewrite of server architecture
- Enhanced all tools with dual-model support
- Improved error messages and user feedback

## [1.0.0] - 2025-06-09

### Added
- Initial release of Gemini MCP Server
- Five core tools:
  - ask_gemini: General question answering
  - gemini_code_review: Code analysis and review
  - gemini_brainstorm: Collaborative brainstorming
  - gemini_test_cases: Test case generation
  - gemini_explain: Concept explanation
- server_info tool for status checking
- Basic MCP protocol implementation
- Installation and update scripts
- Environment variable configuration
- Comprehensive test suite

[Unreleased]: https://github.com/lbds137/council-mcp-server/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/lbds137/council-mcp-server/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/lbds137/council-mcp-server/releases/tag/v1.0.0
