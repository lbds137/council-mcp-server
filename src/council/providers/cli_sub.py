"""Subscription-backed local CLI providers (Antigravity CLI and Claude Code CLI).

When explicitly enabled via environment variables, Council routes matching
model families through local subscription CLIs first (zero per-token API cost),
falling back once to OpenRouter if a CLI is unavailable, quota-gated, or fails
for a non-timeout reason.
"""

import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from typing import Any

from .base import (
    AuthenticationError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    ModelInfo,
    ModelNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

QUOTA_CHECK_TIMEOUT_SECONDS = 15.0
DEFAULT_CLI_TIMEOUT_SECONDS = 180.0

# Child CLI and quota subprocesses inherit ONLY these safe runtime/locale/auth-bus variables.
# API keys (OPENROUTER_API_KEY, ZAI_CODING_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY,
# ANTHROPIC_API_KEY, GITHUB_TOKEN, AWS_*, etc.) and parent Claude routing overrides
# (CLAUDECODE, ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_DEFAULT_*) never cross
# into child processes. DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR remain so Antigravity
# CLI can read its Secret Service sign-in token.
_ALLOWED_CHILD_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "SHELL",
        "TZ",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "DBUS_SESSION_BUS_ADDRESS",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
    }
)

# Antigravity CLI model prefixes actually served by the subscription CLI (`agy models`).
_AGY_NATIVE_PREFIXES = (
    "gemini-4-",
    "gemini-3.8-flash",
    "gemini-pro-orchestrator",
)

# Exhaustive tool denylist for headless `agy` calls so Council calls remain text-in/text-out.
_AGY_DENIED_TOOLS = [
    "command(*)",
    "run_command",
    "command_status",
    "read_terminal",
    "read_file",
    "view_file",
    "view_file_outline",
    "view_code_item",
    "view_content_chunk",
    "grep_search",
    "search_in_file",
    "codebase_search",
    "find_by_name",
    "find_files",
    "list_dir",
    "list_files",
    "glob",
    "write_file",
    "edit_file",
    "create_file",
    "delete_file",
    "notebook_edit",
    "move",
    "multi_edit",
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
    "search_web",
    "read_url_content",
    "browser_subagent",
    "invoke_subagent",
    "define_subagent",
    "manage_subagents",
    "spawn_subagent",
    "send_message",
    "manage_task",
    "manage_inbox",
    "run_workflow",
    "swarm",
    "schedule",
    "ask_question",
    "call_mcp_tool",
    "list_resources",
    "read_resource",
    "mcp_*",
    "mcp__*",
]


class CLITimeoutError(LLMProviderError):
    """Raised when a local subscription CLI times out; never falls back to OpenRouter."""

    def __init__(self, message: str, provider: str = "cli", model: str = ""):
        super().__init__(message, provider=provider, model=model, is_retryable=False)


def _scrubbed_child_env(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal allowlisted environment for child CLI / quota subprocesses."""
    env = {k: v for k, v in os.environ.items() if k in _ALLOWED_CHILD_ENV_KEYS}
    if extra:
        env.update(extra)
    return env


_MODEL_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def is_excluded_model(model_id: str) -> bool:
    """Return True if model_id is globally excluded by repository policy (xAI / Grok)."""
    cleaned = model_id.strip().lower()
    if not cleaned:
        return False
    for tok in re.split(r"[/:\s@~]+", cleaned):
        if not tok:
            continue
        if tok in ("x-ai", "xai") or tok.startswith("grok"):
            return True
    return False


def _normalize_openrouter_candidate(model_id: str) -> str:
    """Normalize bare Gemini/Claude/GLM aliases into vendor/slug form for allowlist checks."""
    cleaned = model_id.strip()
    if not cleaned:
        return ""
    unprefixed = cleaned.removeprefix("~")
    lowered = unprefixed.lower()
    if lowered.startswith("glm-"):
        return f"z-ai/{lowered}"
    if lowered.startswith("gemini-"):
        return f"google/{lowered}"
    if lowered.startswith("claude-"):
        return f"anthropic/{lowered}"
    return lowered


def private_openrouter_providers(openrouter_model_id: str) -> list[str] | None:
    """Return the pinned OpenRouter provider slug(s) allowed under private_only, or None.

    Owner ruling (2026-11-15): private_only OpenRouter calls use a strict vendor+host
    allowlist with `provider.only`, `allow_fallbacks=False`, and `data_collection="deny"`:
    - anthropic/claude-* -> ["anthropic"]
    - openai/<non-oss>   -> ["openai"]
    - google/gemini-*    -> ["google-vertex"] (excludes google/gemma* and AI Studio)
    - mistralai/*        -> ["mistral"]
    - z-ai/glm*          -> ["mistral"] (Mistral host only; Z.ai direct plan stays disabled)
    All other vendors, `:free` / `:variant` suffixes, and `@preset/...` IDs are rejected.
    """
    raw = openrouter_model_id.strip()
    if (
        not raw
        or any(c.isspace() for c in raw)
        or "@" in raw
        or ":" in raw
        or raw.lstrip("~") != raw.removeprefix("~")
    ):
        return None
    if is_excluded_model(raw):
        return None
    normalized = _normalize_openrouter_candidate(raw)
    if "/" not in normalized or ":" in normalized or "@" in normalized:
        return None
    vendor, slug = normalized.split("/", 1)
    if not _MODEL_COMPONENT_RE.fullmatch(vendor) or not _MODEL_COMPONENT_RE.fullmatch(slug):
        return None
    if vendor == "anthropic" and (slug.startswith("claude-") or slug == "claude-latest"):
        return ["anthropic"]
    if vendor == "openai" and not slug.startswith("gpt-oss"):
        return ["openai"]
    if vendor == "google" and slug.startswith("gemini-"):
        return ["google-vertex"]
    if vendor == "mistralai":
        return ["mistral"]
    if vendor == "z-ai" and slug.startswith("glm"):
        return ["mistral"]
    return None


def is_non_private_model(model_id: str) -> bool:
    """Return True if model_id is excluded when private_only=True."""
    return is_excluded_model(model_id) or private_openrouter_providers(model_id) is None


def private_openrouter_extra_body(
    openrouter_model_id: str, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build OpenRouter extra_body enforcing strict allowlist provider pinning."""
    allowed_hosts = private_openrouter_providers(openrouter_model_id)
    if allowed_hosts is None:
        raise LLMProviderError(
            f"Model '{openrouter_model_id}' is excluded when private_only=True",
            provider="privacy-gate",
            model=openrouter_model_id,
            is_retryable=False,
        )
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    prov_raw = merged.get("provider")
    prov: dict[str, Any] = dict(prov_raw) if isinstance(prov_raw, dict) else {}
    prov.pop("ignore", None)
    prov["data_collection"] = "deny"
    prov["only"] = list(allowed_hosts)
    prov["allow_fallbacks"] = False
    merged["provider"] = prov
    return merged


def _truthy_env(name: str) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _run_isolated_subprocess(
    cmd: list[str],
    *,
    input_text: str | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Run cmd in a dedicated process group and SIGKILL the entire group on timeout."""
    if input_text is not None and "\x00" in input_text:
        raise ValueError("input contains NUL byte")
    if any("\x00" in part for part in cmd):
        raise ValueError("command argument contains NUL byte")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        raise
    except BaseException:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        raise

    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _check_quota_gate(cmd_str: str | None, provider_name: str, model: str) -> None:
    """Run an optional quota gate command; non-zero exit raises RateLimitError."""
    if not cmd_str or not cmd_str.strip():
        return
    try:
        argv = shlex.split(cmd_str)
    except ValueError as exc:
        raise LLMProviderError(
            f"invalid quota command syntax: {exc}",
            provider=provider_name,
            model=model,
        ) from exc
    if not argv:
        return
    try:
        proc = _run_isolated_subprocess(
            argv,
            input_text=None,
            env=_scrubbed_child_env(),
            timeout=QUOTA_CHECK_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise LLMProviderError(
            f"quota command not found: {argv[0]}",
            provider=provider_name,
            model=model,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RateLimitError(
            f"quota check timed out after {QUOTA_CHECK_TIMEOUT_SECONDS:.0f}s",
            provider=provider_name,
            model=model,
        ) from exc
    except (OSError, ValueError) as exc:
        raise LLMProviderError(
            f"quota check failed to run: {exc}",
            provider=provider_name,
            model=model,
        ) from exc

    if proc.returncode != 0:
        out_lines = (proc.stdout or "").strip().splitlines()
        summary = out_lines[0][:80] if out_lines else f"exit {proc.returncode}"
        raise RateLimitError(
            f"subscription quota gate closed ({summary})",
            provider=provider_name,
            model=model,
        )


def _parse_model_map(raw: str | None) -> dict[str, str]:
    """Parse comma-separated alias=target pairs or a JSON object mapping."""
    if not raw or not raw.strip():
        return {}
    text = raw.strip()
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                return {
                    str(k).strip().lower(): str(v).strip()
                    for k, v in loaded.items()
                    if str(k).strip() and str(v).strip()
                }
        except ValueError:
            logger.warning("Ignoring invalid JSON in model map environment variable")
            return {}
    mapping: dict[str, str] = {}
    for item in text.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            if k.strip() and v.strip():
                mapping[k.strip().lower()] = v.strip()
    return mapping


class AgyCliProvider(LLMProvider):
    """Subscription provider routing Gemini models through Antigravity CLI (`agy`).

    Prompts are passed via stdin (`--input-format text --output-format json`) so
    large prompts never hit argv E2BIG or appear in `/proc/<pid>/cmdline`.
    Session `--settings` enforces `toolPermission="request-review"`, `agentMode=""`,
    `allowNonWorkspaceAccess=False`, `permissions.allow=[]`, and denies shell, file,
    subagent, web, and MCP tools. Council itself defers TPM credential decryption to
    the first tool call, preventing recursive TPM stalls even if global MCP config exists.
    """

    def __init__(
        self,
        binary: str | None = None,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        quota_cmd: str | None = None,
    ):
        self.binary = (binary or os.getenv("COUNCIL_AGY_BIN") or "agy").strip()
        self.timeout = timeout
        self.quota_cmd = (
            quota_cmd
            if quota_cmd is not None
            else (os.getenv("COUNCIL_AGY_QUOTA_CMD") or os.getenv("COUNCIL_QUOTA_CMD"))
        )
        self.pro_model = (os.getenv("COUNCIL_AGY_PRO_MODEL") or "gemini-4-argon-high").strip()
        self.flash_model = (os.getenv("COUNCIL_AGY_FLASH_MODEL") or "gemini-3.8-flash-high").strip()
        self.custom_map = _parse_model_map(os.getenv("COUNCIL_AGY_MODEL_MAP"))

    @property
    def name(self) -> str:
        return "agy-cli"

    @classmethod
    def is_enabled(cls) -> bool:
        return _truthy_env("COUNCIL_AGY_CLI")

    def is_candidate(self, model_id: str) -> bool:
        lowered = model_id.strip().lower()
        if not lowered or ":" in lowered:
            return False
        stripped = lowered.lstrip("~")
        if lowered in self.custom_map or stripped in self.custom_map:
            return True
        return stripped.startswith("google/gemini-") or stripped.startswith("gemini-")

    def resolve(self, model_id: str) -> str | None:
        if not self.is_candidate(model_id):
            return None
        lowered = model_id.strip().lower()
        if lowered in self.custom_map:
            return self.custom_map[lowered]
        stripped = lowered.lstrip("~")
        if stripped in self.custom_map:
            return self.custom_map[stripped]

        slug = stripped.removeprefix("google/")
        if not slug or slug.startswith("-") or "/" in slug:
            return None
        if slug in ("gemini-pro", "gemini-pro-latest"):
            return self.pro_model
        if slug in ("gemini-flash", "gemini-flash-latest"):
            return self.flash_model
        if any(slug.startswith(prefix) for prefix in _AGY_NATIVE_PREFIXES):
            raw_slug = model_id.strip().lstrip("~")
            if raw_slug.lower().startswith("google/"):
                raw_slug = raw_slug.split("/", 1)[1]
            return raw_slug
        return None

    def is_available(self) -> bool:
        return bool(shutil.which(self.binary))

    def list_models(self) -> list[ModelInfo]:
        if not self.is_available():
            return []
        return [
            ModelInfo(id=f"google/{self.pro_model}", name=self.pro_model, provider="google"),
            ModelInfo(id=f"google/{self.flash_model}", name=self.flash_model, provider="google"),
        ]

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del temperature, max_tokens, kwargs
        if not model or model.startswith("-"):
            raise ModelNotFoundError(
                f"Invalid Antigravity CLI model '{model}'",
                provider=self.name,
                model=model or "",
            )
        if "\x00" in prompt or "\x00" in model:
            raise LLMProviderError(
                "Prompt or model contains invalid NUL byte",
                provider=self.name,
                model=model,
                is_retryable=False,
            )
        if not prompt or not prompt.strip():
            raise LLMProviderError(
                "Prompt must not be empty",
                provider=self.name,
                model=model,
                is_retryable=False,
            )
        exe = shutil.which(self.binary)
        if not exe:
            raise AuthenticationError(
                f"CLI binary '{self.binary}' not found on PATH",
                provider=self.name,
                model=model,
            )

        _check_quota_gate(self.quota_cmd, self.name, model)

        timeout_s = max(5, int(self.timeout))
        child_env = _scrubbed_child_env(extra={"AGY_GUARD_MODE": "strict"})
        with tempfile.TemporaryDirectory(prefix="council-agy-") as tmp_dir:
            settings_path = os.path.join(tmp_dir, "settings.json")
            with open(settings_path, "w", encoding="utf-8") as sfh:
                json.dump(
                    {
                        "toolPermission": "request-review",
                        "allowNonWorkspaceAccess": False,
                        "agentMode": "",
                        "permissions": {
                            "allow": [],
                            "deny": _AGY_DENIED_TOOLS,
                        },
                    },
                    sfh,
                )
            cmd = [
                exe,
                "--input-format",
                "text",
                "--output-format",
                "json",
                "--model",
                model,
                "--sandbox",
                "--settings",
                settings_path,
                "--print-timeout",
                f"{timeout_s}s",
                "--disable-slash-commands",
            ]
            try:
                proc = _run_isolated_subprocess(
                    cmd,
                    input_text=prompt,
                    cwd=tmp_dir,
                    env=child_env,
                    timeout=self.timeout + 5.0,
                )
            except subprocess.TimeoutExpired as exc:
                raise CLITimeoutError(
                    f"CLI timed out after {timeout_s}s",
                    provider=self.name,
                    model=model,
                ) from exc
            except (OSError, ValueError) as exc:
                raise LLMProviderError(
                    f"failed to execute CLI: {exc}",
                    provider=self.name,
                    model=model,
                ) from exc

        if proc.stderr:
            logger.debug("agy stderr (exit %s): %s", proc.returncode, proc.stderr[:300])

        raw_out = (proc.stdout or "").strip()
        if not raw_out:
            raise LLMProviderError(
                f"empty output from CLI (exit {proc.returncode})",
                provider=self.name,
                model=model,
                is_retryable=True,
            )

        try:
            payload = json.loads(raw_out)
        except ValueError as exc:
            raise LLMProviderError(
                f"non-JSON output from CLI (exit {proc.returncode})",
                provider=self.name,
                model=model,
            ) from exc

        if not isinstance(payload, dict):
            raise LLMProviderError("unexpected JSON root from CLI", provider=self.name, model=model)

        if payload.get("finished_reason") == "print_timeout":
            raise CLITimeoutError(
                f"CLI hit print_timeout ({timeout_s}s)",
                provider=self.name,
                model=model,
            )
        if payload.get("denied_actions"):
            raise LLMProviderError(
                "CLI turn aborted after attempting a denied tool action",
                provider=self.name,
                model=model,
            )
        status = payload.get("status")
        if status != "SUCCESS" or proc.returncode != 0:
            raw_err = str(payload.get("error") or "").strip().splitlines()
            err_line = (
                raw_err[0][:120] if raw_err else f"CLI status={status} exit={proc.returncode}"
            )
            lower_err = (err_line + " " + (proc.stderr or "")[:200]).lower()
            if "quota" in lower_err or "rate limit" in lower_err or "429" in lower_err:
                raise RateLimitError(err_line, provider=self.name, model=model)
            raise LLMProviderError(err_line, provider=self.name, model=model)

        content = str(payload.get("response") or "")
        if not content.strip():
            raise LLMProviderError(
                "CLI returned an empty response", provider=self.name, model=model
            )

        reported_model = payload.get("model")
        actual = (
            reported_model.strip()
            if isinstance(reported_model, str) and reported_model.strip()
            else model
        )
        served = actual if "/" in actual else f"google/{actual}"
        return LLMResponse(
            content=content,
            model=served,
            metadata={"route": self.name, "conversation_id": payload.get("conversation_id")},
        )


class ClaudeCliProvider(LLMProvider):
    """Subscription provider routing explicit Anthropic models via `claude -p`."""

    def __init__(
        self,
        binary: str | None = None,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
        quota_cmd: str | None = None,
    ):
        self.binary = (binary or os.getenv("COUNCIL_CLAUDE_BIN") or "claude").strip()
        self.timeout = timeout
        self.quota_cmd = (
            quota_cmd
            if quota_cmd is not None
            else (os.getenv("COUNCIL_CLAUDE_QUOTA_CMD") or os.getenv("COUNCIL_QUOTA_CMD"))
        )
        self.custom_map = _parse_model_map(os.getenv("COUNCIL_CLAUDE_MODEL_MAP"))

    @property
    def name(self) -> str:
        return "claude-cli"

    @classmethod
    def is_enabled(cls) -> bool:
        return _truthy_env("COUNCIL_CLAUDE_CLI")

    def is_candidate(self, model_id: str) -> bool:
        lowered = model_id.strip().lower()
        if not lowered or ":" in lowered:
            return False
        stripped = lowered.lstrip("~")
        if lowered in self.custom_map or stripped in self.custom_map:
            return True
        return stripped.startswith("anthropic/claude") or stripped.startswith("claude-")

    def resolve(self, model_id: str) -> str | None:
        if not self.is_candidate(model_id):
            return None
        lowered = model_id.strip().lower()
        if lowered in self.custom_map:
            return self.custom_map[lowered]
        stripped = lowered.lstrip("~")
        if stripped in self.custom_map:
            return self.custom_map[stripped]

        slug = stripped.removeprefix("anthropic/")
        if not slug or slug.startswith("-") or "/" in slug:
            return None
        if slug in ("claude-opus", "claude-opus-latest"):
            return "opus"
        if slug in ("claude-haiku", "claude-haiku-latest"):
            return "haiku"
        if slug in ("claude-sonnet", "claude-sonnet-latest", "claude-latest"):
            return "sonnet"
        if slug.startswith("claude-"):
            raw_slug = model_id.strip().lstrip("~")
            if raw_slug.lower().startswith("anthropic/"):
                raw_slug = raw_slug.split("/", 1)[1]
            return raw_slug
        return None

    def is_available(self) -> bool:
        return bool(shutil.which(self.binary))

    def list_models(self) -> list[ModelInfo]:
        return []

    @staticmethod
    def _extract_served_model(payload: dict[str, Any], fallback_model: str) -> str:
        raw_model = payload.get("model")
        if isinstance(raw_model, str) and raw_model.strip():
            chosen = raw_model.strip()
        else:
            usage_map = payload.get("modelUsage")
            if isinstance(usage_map, dict) and len(usage_map) == 1:
                only_key = next(iter(usage_map.keys()))
                chosen = str(only_key).strip() or fallback_model
            else:
                chosen = fallback_model
        if "/" in chosen:
            return chosen
        if chosen.startswith("claude-"):
            return f"anthropic/{chosen}"
        return f"anthropic/claude-{chosen}"

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del temperature, max_tokens, kwargs
        if not model or model.startswith("-"):
            raise ModelNotFoundError(
                f"Invalid Claude CLI model '{model}'",
                provider=self.name,
                model=model or "",
            )
        if "\x00" in prompt or "\x00" in model:
            raise LLMProviderError(
                "Prompt or model contains invalid NUL byte",
                provider=self.name,
                model=model,
                is_retryable=False,
            )
        if not prompt or not prompt.strip():
            raise LLMProviderError(
                "Prompt must not be empty",
                provider=self.name,
                model=model,
                is_retryable=False,
            )
        exe = shutil.which(self.binary)
        if not exe:
            raise AuthenticationError(
                f"CLI binary '{self.binary}' not found on PATH",
                provider=self.name,
                model=model,
            )

        _check_quota_gate(self.quota_cmd, self.name, model)

        # Allowlisted child env keeps native subscription auth clean while stripping all API keys
        # and parent Claude routing overrides; prompt arrives over stdin (never argv).
        child_env = _scrubbed_child_env()
        with tempfile.TemporaryDirectory(prefix="council-claude-") as tmp_dir:
            empty_mcp = os.path.join(tmp_dir, "empty-mcp.json")
            with open(empty_mcp, "w", encoding="utf-8") as mfh:
                json.dump({"mcpServers": {}}, mfh)
            cmd = [
                exe,
                "-p",
                "--input-format",
                "text",
                "--output-format",
                "json",
                "--mcp-config",
                empty_mcp,
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--safe-mode",
                "--no-session-persistence",
                "--disable-slash-commands",
                "--tools",
                "",
                "--model",
                model,
            ]
            try:
                proc = _run_isolated_subprocess(
                    cmd,
                    input_text=prompt,
                    cwd=tmp_dir,
                    env=child_env,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise CLITimeoutError(
                    f"CLI timed out after {self.timeout:.0f}s",
                    provider=self.name,
                    model=model,
                ) from exc
            except (OSError, ValueError) as exc:
                raise LLMProviderError(
                    f"failed to execute CLI: {exc}",
                    provider=self.name,
                    model=model,
                ) from exc

        if proc.stderr:
            logger.debug("claude stderr (exit %s): %s", proc.returncode, proc.stderr[:300])

        raw_out = (proc.stdout or "").strip()
        if not raw_out:
            raise LLMProviderError(
                f"empty output from CLI (exit {proc.returncode})",
                provider=self.name,
                model=model,
                is_retryable=True,
            )

        try:
            payload = json.loads(raw_out)
        except ValueError as exc:
            raise LLMProviderError(
                f"non-JSON output from CLI (exit {proc.returncode})",
                provider=self.name,
                model=model,
            ) from exc

        if not isinstance(payload, dict):
            raise LLMProviderError("unexpected JSON root from CLI", provider=self.name, model=model)

        is_err = bool(payload.get("is_error")) or proc.returncode != 0
        content = str(payload.get("result") or "")
        if is_err:
            err_lines = content.strip().splitlines()
            err_line = err_lines[0][:120] if err_lines else f"CLI exited {proc.returncode}"
            lower_err = (err_line + " " + (proc.stderr or "")[:200]).lower()
            if "limit" in lower_err or "quota" in lower_err or "429" in lower_err:
                raise RateLimitError(err_line, provider=self.name, model=model)
            raise LLMProviderError(err_line, provider=self.name, model=model)

        if not content.strip():
            raise LLMProviderError("CLI returned an empty result", provider=self.name, model=model)

        served = self._extract_served_model(payload, model)
        return LLMResponse(
            content=content,
            model=served,
            metadata={"route": self.name},
        )
