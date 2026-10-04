# Council MCP Server: Improvement Ideas

Open ideas, as of 2026-09-24; re-evaluated 2026-09-27 and 2026-10-04. Done and
dropped items are in git history (`git log -- docs/IMPROVEMENT_IDEAS.md`);
streaming Z.ai responses shipped 2026-09-27.

## Maybe

### Conversations that survive a reconnect
Conversation sessions live in memory, so `/mcp` → Reconnect ends them. Saving
them to a small file under `~/.claude-mcp-servers/council/` would keep them.
Worth doing only if multi-turn conversations become a regular habit. Checked
2026-09-27: 11 starts and 2 continues, all on 2026-09-24 (rollout testing), none
since; still none on 2026-10-04.

### Structured request logs
One log line per tool call, with the tool, the model it resolved to, the route
(Z.ai plan or OpenRouter), the time taken and the result. That would make
questions like "how often does the plan fall back?" answerable from the log.
The `server_info` counters cover the basics today, and on 2026-09-27 one pass
over the existing log answered the fallback question. Worth doing if fallback
rates need regular tracking. 2026-10-04: the week since had 4 tool calls in all.

## Decided against

- **Pydantic models for tool schemas**: 17 small, hand-written schemas; the
  tests cover them, and a dependency adds nothing here.
- **Dependency injection or a plugin architecture**: one owner, one process;
  the registry's discovery is enough.
- **devcontainer / Dockerfile**: the server runs on the host, from the venv
  that `install.sh` creates.
