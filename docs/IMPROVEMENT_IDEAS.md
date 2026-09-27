# Council MCP Server: Improvement Ideas

Open ideas, as of 2026-09-24; re-evaluated 2026-09-27. The earlier version of this file (June 2025)
listed a review backlog that has since been done or no longer applies; it is in
git history (`git log -- docs/IMPROVEMENT_IDEAS.md`).

## Next

### Stream Z.ai responses
Z.ai's coding endpoint drops any non-streamed call at 60 s. All three Z.ai
errors in the log (2026-09-24) came exactly 60.0 s after the call started, and
the longest successful call ran 26 s, so every GLM call that needs more than a
minute fails today and falls back to billed OpenRouter a minute late. Our client
timeout is 600 s (`COUNCIL_TIMEOUT`), so the cut is Z.ai's. Confirmed
2026-09-27 with one prompt sent both ways: non-streamed failed with
"Connection error." at 60.5 s; `stream=True` succeeded after 606 s (first chunk
5.1 s). Fix: stream in `providers/zai.py` `generate` and assemble content,
reasoning, finish reason and usage from the chunks.

## Maybe

### Conversations that survive a reconnect
Conversation sessions live in memory, so `/mcp` → Reconnect ends them. Saving
them to a small file under `~/.claude-mcp-servers/council/` would keep them.
Worth doing only if multi-turn conversations become a regular habit. Checked
2026-09-27: 11 starts and 2 continues, all on 2026-09-24 (rollout testing), none
since.

### Structured request logs
One log line per tool call, with the tool, the model it resolved to, the route
(Z.ai plan or OpenRouter), the time taken and the result. That would make
questions like "how often does the plan fall back?" answerable from the log.
The `server_info` counters cover the basics today, and on 2026-09-27 one pass
over the existing log answered the fallback question. Worth doing if fallback
rates need regular tracking.

## Decided against

- **Pydantic models for tool schemas**: 17 small, hand-written schemas; the
  tests cover them, and a dependency adds nothing here.
- **Dependency injection or a plugin architecture**: one owner, one process;
  the registry's discovery is enough.
- **devcontainer / Dockerfile**: the server runs on the host, from the venv
  that `install.sh` creates.
