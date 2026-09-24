# Council MCP Server: Improvement Ideas

Open ideas, as of 2026-09-24. The earlier version of this file (June 2025)
listed a review backlog that has since been done or no longer applies; it is in
git history (`git log -- docs/IMPROVEMENT_IDEAS.md`).

## Worth doing

### Progress notifications for long tools
A `debate` with reasoning models takes minutes (about 4.5 minutes for two GLM
debaters), and the caller sees nothing until it ends. MCP progress
notifications could report each finished turn. Cost: the JSON-RPC layer would
have to send notifications during a call, which it can't do today.

## Maybe

### Conversations that survive a reconnect
Conversation sessions live in memory, so `/mcp` → Reconnect ends them. Saving
them to a small file under `~/.claude-mcp-servers/council/` would keep them.
Worth doing only if multi-turn conversations become a regular habit.

### Structured request logs
One log line per tool call, with the tool, the model it resolved to, the route
(Z.ai plan or OpenRouter), the time taken and the result. That would make
questions like "how often does the plan fall back?" answerable from the log.
The `server_info` counters cover the basics today.

## Decided against

- **Pydantic models for tool schemas**: 17 small, hand-written schemas; the
  tests cover them, and a dependency adds nothing here.
- **Dependency injection or a plugin architecture**: one owner, one process;
  the registry's discovery is enough.
- **devcontainer / Dockerfile**: the server runs on the host, from the venv
  that `install.sh` creates.
