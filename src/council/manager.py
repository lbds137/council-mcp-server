"""Model manager for Council MCP server."""

import logging
import math
import os
import re
from typing import Any

from .providers import (
    AgyCliProvider,
    ClaudeCliProvider,
    CLITimeoutError,
    LLMProviderError,
    LLMResponse,
    ModelInfo,
    OpenRouterProvider,
    ZaiCodingProvider,
    is_excluded_model,
    private_openrouter_extra_body,
    private_openrouter_providers,
)
from .providers.base import AuthenticationError, ModelNotFoundError, RateLimitError

logger = logging.getLogger(__name__)


_CLI_MODEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _cli_fallback_reason(err: LLMProviderError) -> str:
    """Short user-visible summary of a CLI failure without leaking raw subprocess stderr."""
    if isinstance(err, RateLimitError):
        return "quota or rate limit"
    if isinstance(err, AuthenticationError):
        return "CLI unavailable"
    if isinstance(err, ModelNotFoundError):
        return "model unavailable on CLI"
    return "CLI error"


class ModelManager:
    """Manages LLM interactions for Council MCP server.

    This class provides a unified interface for:
    - Generating content from LLMs via local subscription CLIs (`claude`, `agy`),
      the Z.ai coding plan (non-private GLM calls), or OpenRouter
    - Enforcing repository policy and `private_only` vendor/host allowlists
    - Switching between different models and tracking usage statistics
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        cli_timeout: float | None = None,
    ):
        """Initialize the model manager.

        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY.
            default_model: Default model to use. If None, reads from COUNCIL_DEFAULT_MODEL
                          or defaults to "~openai/gpt-sol-latest".
            timeout: Request timeout in seconds. If None, reads from COUNCIL_TIMEOUT
                    or defaults to 600.0 (10 minutes).
            cli_timeout: Local subscription CLI timeout in seconds. If None, reads from
                        COUNCIL_CLI_TIMEOUT (seconds) or defaults to `timeout` (600.0s).
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        # default_model always has a value due to the fallback
        self.default_model: str = (
            default_model
            or os.getenv("COUNCIL_DEFAULT_MODEL", "~openai/gpt-sol-latest")
            or "~openai/gpt-sol-latest"
        )
        self.timeout = timeout or float(os.getenv("COUNCIL_TIMEOUT", "600000")) / 1000
        raw_cli_timeout = os.getenv("COUNCIL_CLI_TIMEOUT")
        if cli_timeout is not None:
            self.cli_timeout = cli_timeout
        elif raw_cli_timeout and raw_cli_timeout.strip():
            try:
                parsed_cli_timeout = float(raw_cli_timeout.strip())
                if not math.isfinite(parsed_cli_timeout) or parsed_cli_timeout <= 0:
                    raise ValueError("must be finite and > 0")
                self.cli_timeout = parsed_cli_timeout
            except ValueError:
                logger.warning(
                    "Invalid COUNCIL_CLI_TIMEOUT=%r; falling back to %.1fs",
                    raw_cli_timeout,
                    self.timeout,
                )
                self.cli_timeout = self.timeout
        else:
            self.cli_timeout = self.timeout

        # Initialize the providers
        self._provider: OpenRouterProvider | None = None
        self.zai_api_key = os.getenv("ZAI_CODING_API_KEY")
        self._zai_provider: ZaiCodingProvider | None = None
        self.agy_cli_enabled = AgyCliProvider.is_enabled()
        self._agy_provider: AgyCliProvider | None = None
        self.claude_cli_enabled = ClaudeCliProvider.is_enabled()
        self._claude_provider: ClaudeCliProvider | None = None

        # Current active model (can be changed with set_model)
        self._active_model: str = self.default_model

        # Statistics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.zai_calls = 0  # requests tried on the plan
        self.zai_fallbacks = 0  # of those, retried on OpenRouter after failing
        self.zai_unavailable = 0  # GLM requests sent to OpenRouter unchecked: no model list
        self.agy_calls = 0
        self.agy_fallbacks = 0
        self.claude_calls = 0
        self.claude_fallbacks = 0

        logger.info(f"ModelManager initialized with default model: {self.default_model}")

    @property
    def provider(self) -> OpenRouterProvider:
        """Get the OpenRouter provider, initializing if needed."""
        if self._provider is None:
            self._provider = OpenRouterProvider(
                api_key=self.api_key,
                default_model=self.default_model,
                timeout=self.timeout,
            )
        return self._provider

    @property
    def zai_provider(self) -> ZaiCodingProvider | None:
        """Get the Z.ai coding-plan provider, or None when no key is configured."""
        if self._zai_provider is None and self.zai_api_key:
            self._zai_provider = ZaiCodingProvider(api_key=self.zai_api_key, timeout=self.timeout)
        return self._zai_provider

    @property
    def agy_provider(self) -> AgyCliProvider | None:
        """Get the Antigravity CLI subscription provider when COUNCIL_AGY_CLI=1."""
        if self._agy_provider is None and self.agy_cli_enabled:
            self._agy_provider = AgyCliProvider(timeout=self.cli_timeout)
        return self._agy_provider

    @property
    def claude_provider(self) -> ClaudeCliProvider | None:
        """Get the Claude CLI subscription provider when COUNCIL_CLAUDE_CLI=1."""
        if self._claude_provider is None and self.claude_cli_enabled:
            self._claude_provider = ClaudeCliProvider(timeout=self.cli_timeout)
        return self._claude_provider

    @property
    def active_model(self) -> str:
        """Get the currently active model."""
        return self._active_model

    def set_model(self, model_id: str) -> bool:
        """Set the active model for subsequent requests.

        Args:
            model_id: The model ID to use (e.g., "~moonshotai/kimi-latest").

        Returns:
            True if the model was set successfully.
        """
        if is_excluded_model(model_id):
            raise LLMProviderError(
                f"Model '{model_id}' is excluded by policy",
                provider="policy-gate",
                model=model_id,
            )
        logger.info(f"Setting active model to: {model_id}")
        self._active_model = model_id
        return True

    def generate_content(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """Generate content from the LLM.

        This method provides backward compatibility with the old DualModelManager
        interface by returning a tuple of (content, model_used).

        Args:
            prompt: The prompt to send to the model.
            model: Override model for this request. If None, uses active model.
            **kwargs: Additional parameters passed to the provider.

        Returns:
            Tuple of (response_content, model_used). model_used names the model
            that served the request, plus its route when a subscription lane was tried.

        Raises:
            LLMProviderError: If generation fails.
        """
        response, model_used = self._generate(prompt, model, **kwargs)
        return response.content, model_used

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate content and return full response object.

        Args:
            prompt: The prompt to send to the model.
            model: Override model for this request. If None, uses active model.
            **kwargs: Additional parameters passed to the provider.

        Returns:
            LLMResponse object with content and metadata.

        Raises:
            LLMProviderError: If generation fails.
        """
        response, _ = self._generate(prompt, model, **kwargs)
        return response

    @staticmethod
    def _is_private_cli_target(resolved: str, *, family: str) -> bool:
        """Return True if a resolved local CLI model target is cleared for private_only."""
        cleaned = resolved.strip()
        if not cleaned or not _CLI_MODEL_TOKEN_RE.fullmatch(cleaned) or is_excluded_model(cleaned):
            return False
        lowered = cleaned.lower()
        if family == "claude":
            return lowered in ("opus", "sonnet", "haiku") or lowered.startswith("claude-")
        if family == "agy":
            return lowered.startswith(("gemini-", "claude-"))
        return False

    def is_private_allowed_model(self, model_id: str) -> bool:
        """Return True if model_id is allowed under private_only=True on this manager."""
        if not isinstance(model_id, str) or not model_id.strip() or is_excluded_model(model_id):
            return False
        agy = self.agy_provider
        agy_model = agy.resolve(model_id) if agy else None
        if isinstance(agy_model, str) and not self._is_private_cli_target(agy_model, family="agy"):
            return False
        claude = self.claude_provider
        claude_model = claude.resolve(model_id) if claude else None
        if isinstance(claude_model, str) and not self._is_private_cli_target(
            claude_model, family="claude"
        ):
            return False
        if isinstance(agy_model, str) or isinstance(claude_model, str):
            return True
        return private_openrouter_providers(self._openrouter_id(model_id)) is not None

    def _generate(self, prompt: str, model: str | None, **kwargs: Any) -> tuple[LLMResponse, str]:
        """Route a request and return the response with a label naming its route.

        Subscription routes (Z.ai coding plan when non-private, Antigravity CLI, Claude CLI
        when enabled) run first; everything else, and any non-timeout subscription failure,
        falls back once to OpenRouter.
        """
        private_only = bool(kwargs.pop("private_only", False))
        model_to_use = model or self._active_model
        self.total_calls += 1

        if "\x00" in prompt or "\x00" in model_to_use:
            self.failed_calls += 1
            raise LLMProviderError(
                "Prompt or model contains invalid NUL byte",
                provider="input-gate",
                model=model_to_use,
                is_retryable=False,
            )

        if not prompt or not prompt.strip():
            self.failed_calls += 1
            raise LLMProviderError(
                "Prompt must not be empty",
                provider="input-gate",
                model=model_to_use,
                is_retryable=False,
            )

        if is_excluded_model(model_to_use):
            self.failed_calls += 1
            raise LLMProviderError(
                f"Model '{model_to_use}' is excluded by policy",
                provider="policy-gate",
                model=model_to_use,
            )

        or_id = self._openrouter_id(model_to_use)
        zai = None if private_only else self.zai_provider
        zai_model = zai.resolve(model_to_use) if zai else None
        # Read the reason now, next to the resolve that produced it: a parallel
        # call (e.g. a debate) can fetch the list again and change list_error
        # while this call waits on OpenRouter
        unavailable = (
            zai.list_error
            if zai is not None and zai_model is None and zai.is_candidate(model_to_use)
            else None
        )
        agy = self.agy_provider
        agy_model = agy.resolve(model_to_use) if agy else None
        claude = self.claude_provider
        claude_model = claude.resolve(model_to_use) if claude else None

        if private_only:
            if isinstance(agy_model, str) and not self._is_private_cli_target(
                agy_model, family="agy"
            ):
                self.failed_calls += 1
                raise LLMProviderError(
                    f"Resolved CLI model for '{model_to_use}' is excluded when private_only=True",
                    provider="privacy-gate",
                    model=model_to_use,
                )
            if isinstance(claude_model, str) and not self._is_private_cli_target(
                claude_model, family="claude"
            ):
                self.failed_calls += 1
                raise LLMProviderError(
                    f"Resolved CLI model for '{model_to_use}' is excluded when private_only=True",
                    provider="privacy-gate",
                    model=model_to_use,
                )
            if (
                agy_model is None
                and claude_model is None
                and private_openrouter_providers(or_id) is None
            ):
                self.failed_calls += 1
                raise LLMProviderError(
                    f"Model '{model_to_use}' is excluded when private_only=True",
                    provider="privacy-gate",
                    model=model_to_use,
                )

        try:
            if zai is not None and zai_model is not None:
                response, model_used = self._generate_on_plan(
                    zai, prompt, model_to_use, zai_model, **kwargs
                )
            elif agy is not None and agy_model is not None:
                response, model_used = self._generate_on_cli(
                    agy,
                    "Antigravity CLI",
                    "agy",
                    prompt,
                    model_to_use,
                    agy_model,
                    private_only=private_only,
                    **kwargs,
                )
            elif claude is not None and claude_model is not None:
                response, model_used = self._generate_on_cli(
                    claude,
                    "Claude CLI",
                    "claude",
                    prompt,
                    model_to_use,
                    claude_model,
                    private_only=private_only,
                    **kwargs,
                )
            else:
                or_kwargs = dict(kwargs)
                if private_only:
                    or_kwargs["extra_body"] = private_openrouter_extra_body(
                        or_id, or_kwargs.get("extra_body")
                    )
                response = self.provider.generate(prompt, model=or_id, **or_kwargs)
                model_used = response.model
                if unavailable:
                    # A key is set but the plan couldn't be consulted: say so,
                    # or a broken key would silently bill every GLM call
                    self.zai_unavailable += 1
                    model_used += f" · OpenRouter (Z.ai unavailable: {unavailable})"
        except LLMProviderError as e:
            self.failed_calls += 1
            logger.error(f"Generation failed: {e}")
            raise

        self.successful_calls += 1
        return response, model_used

    def _generate_on_cli(
        self,
        cli_provider: AgyCliProvider | ClaudeCliProvider,
        label: str,
        stat_prefix: str,
        prompt: str,
        requested: str,
        resolved_model: str,
        *,
        private_only: bool = False,
        **kwargs: Any,
    ) -> tuple[LLMResponse, str]:
        """Try a local subscription CLI once; fall back to OpenRouter unless timed out."""
        if stat_prefix == "agy":
            self.agy_calls += 1
        else:
            self.claude_calls += 1
        try:
            response = cli_provider.generate(prompt, model=resolved_model, **kwargs)
            return response, f"{response.model} · {label}"
        except CLITimeoutError:
            # Never fall back to OpenRouter after a CLI timeout (avoids 2x timeout stalls).
            raise
        except LLMProviderError as cli_error:
            or_id = self._openrouter_id(requested)
            or_kwargs = dict(kwargs)
            if private_only:
                # Fails closed with LLMProviderError if `or_id` is outside the allowlist.
                try:
                    or_kwargs["extra_body"] = private_openrouter_extra_body(
                        or_id, or_kwargs.get("extra_body")
                    )
                except LLMProviderError as gate_error:
                    raise LLMProviderError(
                        f"{label} failed ({cli_error}); fallback blocked: {gate_error}",
                        provider=cli_provider.name,
                        model=resolved_model,
                        is_retryable=False,
                    ) from gate_error
            logger.warning(
                f"{label} failed for {resolved_model}, retrying on OpenRouter: {cli_error}"
            )
            if stat_prefix == "agy":
                self.agy_fallbacks += 1
            else:
                self.claude_fallbacks += 1
            try:
                response = self.provider.generate(prompt, model=or_id, **or_kwargs)
            except LLMProviderError as openrouter_error:
                raise LLMProviderError(
                    f"{label}: {cli_error}; OpenRouter fallback: {openrouter_error}",
                    provider=cli_provider.name,
                    model=resolved_model,
                    is_retryable=cli_error.is_retryable,
                ) from openrouter_error
            reason = _cli_fallback_reason(cli_error)
            return response, f"{response.model} · OpenRouter ({label} failed: {reason})"

    def _generate_on_plan(
        self,
        zai: ZaiCodingProvider,
        prompt: str,
        requested: str,
        zai_model: str,
        **kwargs: Any,
    ) -> tuple[LLMResponse, str]:
        """Try the Z.ai plan once, then fall back to OpenRouter once."""
        self.zai_calls += 1
        try:
            response = zai.generate(prompt, model=zai_model, **kwargs)
            return response, f"{response.model} · Z.ai plan"
        except LLMProviderError as zai_error:
            logger.warning(f"Z.ai plan failed for {zai_model}, retrying on OpenRouter: {zai_error}")
            self.zai_fallbacks += 1
            try:
                response = self.provider.generate(
                    prompt, model=self._openrouter_id(requested), **kwargs
                )
            except LLMProviderError as openrouter_error:
                raise LLMProviderError(
                    f"Z.ai plan: {zai_error}; OpenRouter fallback: {openrouter_error}",
                    provider="zai-coding",
                    model=zai_model,
                    is_retryable=zai_error.is_retryable,
                ) from openrouter_error
            reason = str(zai_error)[:80]
            return response, f"{response.model} · OpenRouter (Z.ai failed: {reason})"

    @staticmethod
    def _strip_agy_effort_suffix(gemini_slug: str) -> str:
        """Strip Antigravity CLI effort suffixes (-xhigh/-high/-medium/-low) for OpenRouter."""
        lowered = gemini_slug.lower()
        for suffix in ("-xhigh", "-high", "-medium", "-low"):
            if lowered.endswith(suffix) and len(gemini_slug) > len(suffix):
                return gemini_slug[: -len(suffix)]
        return gemini_slug

    @staticmethod
    def _openrouter_id(model_id: str) -> str:
        """OpenRouter's ID for a model: normalize bare GLM, Gemini, and Claude IDs."""
        cleaned = model_id.strip()
        if not cleaned:
            return cleaned
        has_tilde = cleaned.startswith("~")
        unprefixed = cleaned.lstrip("~")
        lowered = unprefixed.lower()
        if lowered.startswith("glm-"):
            if lowered == "glm-latest":
                return "~z-ai/glm-latest"
            return f"z-ai/{unprefixed}"
        if lowered.startswith("gemini-"):
            if lowered in ("gemini-pro", "gemini-pro-latest"):
                return "~google/gemini-pro-latest"
            if lowered in ("gemini-flash", "gemini-flash-latest"):
                return "~google/gemini-flash-latest"
            slug = ModelManager._strip_agy_effort_suffix(unprefixed)
            return f"{'~' if has_tilde else ''}google/{slug}"
        if lowered.startswith("google/gemini-"):
            slug = ModelManager._strip_agy_effort_suffix(unprefixed.split("/", 1)[1])
            return f"{'~' if has_tilde else ''}google/{slug}"
        if lowered.startswith("claude-"):
            if lowered in ("claude-opus", "claude-opus-latest"):
                return "~anthropic/claude-opus-latest"
            if lowered in ("claude-haiku", "claude-haiku-latest"):
                return "~anthropic/claude-haiku-latest"
            if lowered in ("claude-sonnet", "claude-sonnet-latest", "claude-latest"):
                return "~anthropic/claude-sonnet-latest"
            return f"{'~' if has_tilde else ''}anthropic/{unprefixed}"
        return cleaned

    def list_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List available models (excluding globally disallowed vendors)."""
        return [
            m
            for m in self.provider.list_models(force_refresh=force_refresh)
            if not is_excluded_model(m.id)
        ]

    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """Get information about a specific model."""
        if is_excluded_model(model_id):
            return None
        return self.provider.get_model_info(model_id)

    def is_available(self) -> bool:
        """Check if the model manager is properly configured."""
        return self.provider.is_available()

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        success_rate = (
            (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0
        )
        return {
            "provider": "openrouter",
            "active_model": self._active_model,
            "default_model": self.default_model,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": f"{success_rate:.1f}%",
            "zai_configured": bool(self.zai_api_key),
            "zai_calls": self.zai_calls,
            "zai_fallbacks": self.zai_fallbacks,
            "zai_unavailable": self.zai_unavailable,
            "agy_cli_enabled": self.agy_cli_enabled,
            "agy_calls": self.agy_calls,
            "agy_fallbacks": self.agy_fallbacks,
            "claude_cli_enabled": self.claude_cli_enabled,
            "claude_calls": self.claude_calls,
            "claude_fallbacks": self.claude_fallbacks,
        }
