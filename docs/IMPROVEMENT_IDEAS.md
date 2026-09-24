# Council MCP Server: Improvement Ideas

Open ideas, as of 2026-09-24. The earlier version of this file (June 2025)
listed a review backlog that has since been done or no longer applies; it is in
git history (`git log -- docs/IMPROVEMENT_IDEAS.md`).

## Maybe

### Stream Z.ai responses
Twice on 2026-09-24 a Z.ai plan call failed with "Connection error." exactly
60.0 s after it started (glm-5.3-flash at 14:33:55, glm-5.3 at 16:30:05), well
inside our 180 s timeout. Something on Z.ai's side appears to drop a connection
that has sent nothing for 60 s. The OpenRouter retry covered both, but the retry
costs money and a minute. Streaming the response (`stream=True`) would keep
bytes flowing while GLM reasons. Worth doing if the log keeps showing it:
`grep "Z.ai error" ~/.claude-mcp-servers/council/logs/council-mcp-server.log`.

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
