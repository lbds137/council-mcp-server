# Changelog

All notable changes to the Gemini MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive test coverage for JSON-RPC layer (30 tests)
- Complete test suite for main.py entry point (16 tests)
- Full test coverage for DualModelManager (15 tests)
- Test suite for BrainstormTool (12 tests)
- Python path setup in conftest.py for proper test imports
- python-dotenv to install_requires
- Type annotations throughout the codebase

### Changed
- Python version requirement updated to 3.9+ (required by google-generativeai)
- Test coverage increased from 49% to 80%
- Entry point in setup.py corrected to gemini_mcp.main:main

### Fixed
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

[Unreleased]: https://github.com/lbds137/gemini-mcp-server/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/lbds137/gemini-mcp-server/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/lbds137/gemini-mcp-server/releases/tag/v1.0.0
