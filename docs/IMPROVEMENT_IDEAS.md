# Council MCP Server: Improvement Ideas

Open ideas, as of 2026-09-24; re-evaluated 2026-09-27 and 2026-10-04. Done and
dropped items are in git history (`git log -- docs/IMPROVEMENT_IDEAS.md`);
streaming Z.ai responses shipped 2026-09-27. Performance review 2026-11-10
(measured, then one read-only Fable review) added the deferred and ruled-out
items below.

## Deferred (trigger: Lila un-parks council)

### Decrypt the keys on the first tool call, not at startup
`main.py:74` decrypts `keys.cred` in `CouncilMCPServer.__init__`. Measured
2026-11-10 from the log: median 3.2 s, mean 3.5 s, over 76 non-interleaved
starts since 11-01; about 10 starts a day; 0 tool calls in that time (15 in
all of October). So nearly every decrypt serves a session that never calls
council, and the startup decrypts are what contend for the TPM (keyless starts
2026-11-03 13:34 twice, 11-07 18:01, the 09-24 pile-up). The lazy retry path
already exists (`main.py:288-298`). Saves ~33 s/day of TPM time; the first
tool call pays ~3.3 s instead. Watch for: `handle_initialize`
(`main.py:214-225`) must not log ERROR for a deferred decrypt; `.env` would
then load before the credential (the live `.env` holds no key); 39 test
references to `load_credentials`. Ship together with the next item.

### PID in the log format
`main.py:402`: add `%(process)d`. Interleaved starts (11-09 08:05:56 and
08:05:59) can't be told apart today, which hides lock waits from decrypt
time.

## Maybe

### Lazy `openai` import
`providers/openrouter.py:9`, `providers/zai.py:15`: 0.46 s of the 0.59 s
import, ~4.6 s/day in the background. 26 test patches target the module-level
`OpenAI`, so the rewrite costs more than it saves on its own. Worth doing only
after the deferred decrypt change, if startup time still matters.

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
- **Performance items, ruled out 2026-11-10 (savings under the fix's cost):**
  startup log noise (`core/registry.py:83`, `json_rpc.py:86`, the second
  `_load_env_file()` at `main.py:212`; 346 KB per 10 days against 10 MB x 5
  rotation); CI running on both `push` and `pull_request` (`ci.yml:4-7`,
  ~2 free runner-minutes per push, no wall-clock, and branches without a PR
  would lose CI); CI step speedups (uv ~10 s, mypy cache ~5 s, coverage ~4 s;
  CI at ~62 s/job isn't the critical path, the ~90 s review is); the
  automerge `sleep 30` (`claude-code-review.yml:181`, guards Dependabot
  merges, shared template); the test suite (623 tests in 3 s) and tool
  discovery (~4 ms).
