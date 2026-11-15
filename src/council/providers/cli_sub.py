"""Subscription-backed local CLI providers (Antigravity CLI and Claude Code CLI).

When explicitly enabled via environment variables, Council routes matching
model families through local subscription CLIs first (zero per-token API cost),
falling back once to OpenRouter if a CLI is unavailable, quota-gated, or fails.
"""

import json
import logging
import os
import shlex
import shutil
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

# Non-private model vendor prefixes and bare ID prefixes excluded when private_only=True.
NON_PRIVATE_VENDORS = frozenset(
    {
        "openrouter",
        "z-ai",
        "zai",
        "deepseek",
        "moonshotai",
        "qwen",
        "alibaba",
        "minimax",
        "01-ai",
        "baichuan",
        "bytedance",
        "stepfun",
        "tencent",
        "thudm",
        "baidu",
        "sensetime",
        "siliconflow",
        "novita",
        "xiaomi",
        "x-ai",
    }
)
NON_PRIVATE_BARE_PREFIXES = (
    "glm-",
    "glm4",
    "chatglm",
    "deepseek-",
    "kimi-",
    "qwen",
    "qwq-",
    "minimax-",
    "yi-",
    "doubao-",
    "hunyuan-",
    "ernie-",
    "step-",
    "mimo-",
    "grok-",
    "gpt-oss",
)

# Canonical OpenRouter provider slugs excluded when private_only=True.
NON_PRIVATE_OR_PROVIDERS = [
    "z-ai",
    "deepseek",
    "moonshotai",
    "alibaba",
    "minimax",
    "siliconflow",
    "novita",
    "xai",
    "baidu",
    "byteplus",
    "stepfun",
    "tencent",
    "xiaomi",
    "antdigital",
    "01ai",
    "google-ai-studio",
]

# Secret and routing variables scrubbed from child CLI / quota subprocesses so:
# 1. Child processes never inherit decrypted API keys or trigger eager MCP credential decrypts.
# 2. Parent Claude routing overrides (e.g. ANTHROPIC_BASE_URL) never hijack subscription auth.
_SCRUBBED_ENV_KEYS = frozenset(
    {
        "CLAUDECODE",
        "OPENROUTER_API_KEY",
        "ZAI_CODING_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
    }
)


def _scrubbed_child_env() -> dict[str, str]:
    """Return a copy of os.environ without API keys or parent CLI routing overrides."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _SCRUBBED_ENV_KEYS and not k.startswith("ANTHROPIC_DEFAULT_")
    }


def is_non_private_model(model_id: str) -> bool:
    """Return True if model_id belongs to a provider/route excluded under private_only."""
    cleaned = model_id.strip().lower().lstrip("~")
    if ":free" in cleaned:
        return True
    if "/" in cleaned:
        vendor = cleaned.split("/", 1)[0]
        if vendor in NON_PRIVATE_VENDORS:
            return True
        cleaned = cleaned.split("/", 1)[1]
    base = cleaned.split(":", 1)[0]
    return any(base.startswith(prefix) for prefix in NON_PRIVATE_BARE_PREFIXES)


def private_openrouter_extra_body(
    openrouter_model_id: str, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build OpenRouter extra_body enforcing data_collection=deny and cleared host routing."""
    merged: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    prov_raw = merged.get("provider")
    prov: dict[str, Any] = dict(prov_raw) if isinstance(prov_raw, dict) else {}
    prov["data_collection"] = "deny"

    stripped = openrouter_model_id.strip().lower().lstrip("~")
    if stripped.startswith("google/"):
        # Pin Google models on OpenRouter to Vertex AI (avoiding uncleared AI Studio routes)
        prov["only"] = ["google-vertex"]
        prov["allow_fallbacks"] = False
    else:
        ignored = list(prov.get("ignore") or [])
        for slug in NON_PRIVATE_OR_PROVIDERS:
            if slug not in ignored:
                ignored.append(slug)
        prov["ignore"] = ignored

    merged["provider"] = prov
    return merged


def _truthy_env(name: str) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    return val in ("1", "true", "yes", "on")


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
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            env=_scrubbed_child_env(),
            capture_output=True,
            text=True,
            timeout=QUOTA_CHECK_TIMEOUT_SECONDS,
            check=False,
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
    except OSError as exc:
        raise LLMProviderError(
            f"quota check failed to run: {exc}",
            provider=provider_name,
            model=model,
        ) from exc

    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr or f"exit {proc.returncode}").strip().splitlines()
        summary = detail[0][:120] if detail else f"exit {proc.returncode}"
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
    """Subscription provider routing Google/Gemini models through Antigravity CLI (`agy`)."""

    def __init__(
        self,
        binary: str | None = None,
        timeout: float = 180.0,
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

    @staticmethod
    def is_candidate(model_id: str) -> bool:
        lowered = model_id.strip().lower()
        if ":" in lowered:
            return False
        stripped = lowered.lstrip("~")
        return stripped.startswith("google/") or stripped.startswith("gemini-")

    def resolve(self, model_id: str) -> str | None:
        if not self.is_candidate(model_id):
            return None
        lowered = model_id.strip().lower()
        if lowered in self.custom_map:
            return self.custom_map[lowered]
        stripped = lowered.lstrip("~")
        if stripped in self.custom_map:
            return self.custom_map[stripped]
        if stripped in ("gemini-pro", "gemini-pro-latest"):
            return self.pro_model
        if stripped in ("gemini-flash", "gemini-flash-latest"):
            return self.flash_model
        if stripped.startswith("gemini-"):
            return model_id.strip().lstrip("~")
        slug = stripped.removeprefix("google/")
        if not slug or slug.startswith("-"):
            return None
        if "flash" in slug:
            return self.flash_model
        if "pro" in slug or slug.endswith("-latest"):
            return self.pro_model
        return slug

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
        exe = shutil.which(self.binary)
        if not exe:
            raise AuthenticationError(
                f"CLI binary '{self.binary}' not found on PATH",
                provider=self.name,
                model=model,
            )

        _check_quota_gate(self.quota_cmd, self.name, model)

        timeout_s = max(5, int(self.timeout))
        child_env = _scrubbed_child_env()
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
                            "deny": [
                                "command(*)",
                                "mcp__*",
                                "search_web",
                                "spawn_subagent",
                                "run_workflow",
                                "write_file",
                                "edit_file",
                            ],
                        },
                    },
                    sfh,
                )
            cmd = [
                exe,
                f"--print={prompt}",
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
                proc = subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    cwd=tmp_dir,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout + 5.0,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise LLMProviderError(
                    f"CLI timed out after {timeout_s}s",
                    provider=self.name,
                    model=model,
                    is_retryable=True,
                ) from exc
            except OSError as exc:
                raise LLMProviderError(
                    f"failed to execute CLI: {exc}",
                    provider=self.name,
                    model=model,
                ) from exc

        raw_out = (proc.stdout or "").strip()
        if not raw_out:
            err_msg = (proc.stderr or f"exit {proc.returncode}").strip()[:160]
            raise LLMProviderError(
                f"empty output from CLI ({err_msg})",
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
            raise LLMProviderError(
                f"CLI hit print_timeout ({timeout_s}s)",
                provider=self.name,
                model=model,
                is_retryable=True,
            )
        if payload.get("denied_actions"):
            raise LLMProviderError(
                "CLI turn aborted after attempting a denied tool action",
                provider=self.name,
                model=model,
            )
        status = payload.get("status")
        if status != "SUCCESS" or proc.returncode != 0:
            err_text = str(payload.get("error") or proc.stderr or f"status={status}").strip()
            lower_err = err_text.lower()
            if "quota" in lower_err or "rate" in lower_err or "429" in lower_err:
                raise RateLimitError(err_text[:160], provider=self.name, model=model)
            raise LLMProviderError(
                err_text[:160] or f"CLI exited {proc.returncode}",
                provider=self.name,
                model=model,
            )

        content = str(payload.get("response") or "")
        if not content.strip():
            raise LLMProviderError(
                "CLI returned an empty response", provider=self.name, model=model
            )

        served = model if "/" in model else f"google/{model}"
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
        timeout: float = 180.0,
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

    @staticmethod
    def is_candidate(model_id: str) -> bool:
        lowered = model_id.strip().lower()
        if ":" in lowered:
            return False
        stripped = lowered.lstrip("~")
        return stripped.startswith("anthropic/") or stripped.startswith("claude-")

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
        if not slug or slug.startswith("-"):
            return None
        if "opus" in slug:
            return "opus"
        if "haiku" in slug:
            return "haiku"
        if "sonnet" in slug or slug == "claude-latest":
            return "sonnet"
        return slug

    def is_available(self) -> bool:
        return bool(shutil.which(self.binary))

    def list_models(self) -> list[ModelInfo]:
        return []

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
        exe = shutil.which(self.binary)
        if not exe:
            raise AuthenticationError(
                f"CLI binary '{self.binary}' not found on PATH",
                provider=self.name,
                model=model,
            )

        _check_quota_gate(self.quota_cmd, self.name, model)

        # Scrub parent routing overrides and keys so native subscription auth is used,
        # ignore user/project/local settings, disable MCP/tools/slash-commands, and place
        # prompt after `--` so leading dashes cannot be parsed as CLI flags.
        child_env = _scrubbed_child_env()
        with tempfile.TemporaryDirectory(prefix="council-claude-") as tmp_dir:
            empty_mcp = os.path.join(tmp_dir, "empty-mcp.json")
            with open(empty_mcp, "w", encoding="utf-8") as mfh:
                json.dump({"mcpServers": {}}, mfh)
            cmd = [
                exe,
                "-p",
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
                "--",
                prompt,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    cwd=tmp_dir,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise LLMProviderError(
                    f"CLI timed out after {self.timeout:.0f}s",
                    provider=self.name,
                    model=model,
                    is_retryable=True,
                ) from exc
            except OSError as exc:
                raise LLMProviderError(
                    f"failed to execute CLI: {exc}",
                    provider=self.name,
                    model=model,
                ) from exc

        raw_out = (proc.stdout or "").strip()
        if not raw_out:
            err_msg = (proc.stderr or f"exit {proc.returncode}").strip()[:160]
            raise LLMProviderError(
                f"empty output from CLI ({err_msg})",
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
            err_text = (content or proc.stderr or f"exit {proc.returncode}").strip()
            lower_err = err_text.lower()
            if "limit" in lower_err or "quota" in lower_err or "429" in lower_err:
                raise RateLimitError(err_text[:160], provider=self.name, model=model)
            raise LLMProviderError(err_text[:160], provider=self.name, model=model)

        if not content.strip():
            raise LLMProviderError("CLI returned an empty result", provider=self.name, model=model)

        if "/" in model:
            served = model
        elif model.startswith("claude-"):
            served = f"anthropic/{model}"
        else:
            served = f"anthropic/claude-{model}"
        return LLMResponse(
            content=content,
            model=served,
            metadata={"route": self.name},
        )
