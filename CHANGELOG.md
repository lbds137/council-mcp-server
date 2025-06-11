# Changelog

All notable changes to the Gemini MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CHANGELOG.md to track version history
- Improved project structure documentation in README.md
- PyCharm setup documentation
- Test runner scripts for IDE integration

### Fixed
- Corrected project structure in README.md to match actual files
- Updated .claude/settings.json to be Python-focused instead of Node.js
- Fixed pytest/PyCharm integration by moving stdout/stderr modifications to main()
- Resolved "Bad file descriptor" errors when running tests

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