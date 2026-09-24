"""Model manager for Council MCP server."""

import logging
import os
from typing import Any

from .providers import (
    LLMProviderError,
    LLMResponse,
    ModelInfo,
    OpenRouterProvider,
    ZaiCodingProvider,
)

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages LLM interactions for Council MCP server.

    This class provides a unified interface for:
    - Generating content from LLMs via OpenRouter, or via the Z.ai coding plan
      for GLM models when ZAI_CODING_API_KEY is set
    - Switching between different models
    - Tracking usage statistics
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ):
        """Initialize the model manager.

        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY.
            default_model: Default model to use. If None, reads from COUNCIL_DEFAULT_MODEL
                          or defaults to "~openai/gpt-sol-latest".
            timeout: Request timeout in seconds. If None, reads from COUNCIL_TIMEOUT
                    or defaults to 600.0 (10 minutes).
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        # default_model always has a value due to the fallback
        self.default_model: str = (
            default_model
            or os.getenv("COUNCIL_DEFAULT_MODEL", "~openai/gpt-sol-latest")
            or "~openai/gpt-sol-latest"
        )
        self.timeout = timeout or float(os.getenv("COUNCIL_TIMEOUT", "600000")) / 1000

        # Initialize the providers
        self._provider: OpenRouterProvider | None = None
        self.zai_api_key = os.getenv("ZAI_CODING_API_KEY")
        self._zai_provider: ZaiCodingProvider | None = None

        # Current active model (can be changed with set_model)
        self._active_model: str = self.default_model

        # Statistics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.zai_calls = 0  # requests tried on the plan
        self.zai_fallbacks = 0  # of those, retried on OpenRouter after failing
        self.zai_unavailable = 0  # GLM requests sent to OpenRouter unchecked: no model list

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
            that served the request, plus its route when the Z.ai plan was tried.

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

    def _generate(self, prompt: str, model: str | None, **kwargs: Any) -> tuple[LLMResponse, str]:
        """Route a request and return the response with a label naming its route.

        GLM models the Z.ai plan carries go there first; everything else, and
        any plan failure, goes to OpenRouter.
        """
        model_to_use = model or self._active_model
        self.total_calls += 1

        zai = self.zai_provider
        zai_model = zai.resolve(model_to_use) if zai else None
        try:
            if zai is None or zai_model is None:
                response = self.provider.generate(
                    prompt, model=self._openrouter_id(model_to_use), **kwargs
                )
                model_used = response.model
                if zai is not None and zai.list_error and zai.is_candidate(model_to_use):
                    # A key is set but the plan couldn't be consulted: say so,
                    # or a broken key would silently bill every GLM call
                    self.zai_unavailable += 1
                    model_used += f" · OpenRouter (Z.ai unavailable: {zai.list_error})"
            else:
                response, model_used = self._generate_on_plan(
                    zai, prompt, model_to_use, zai_model, **kwargs
                )
        except LLMProviderError as e:
            self.failed_calls += 1
            logger.error(f"Generation failed: {e}")
            raise

        self.successful_calls += 1
        return response, model_used

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
    def _openrouter_id(model_id: str) -> str:
        """OpenRouter's ID for a model: bare GLM IDs need the "z-ai/" prefix."""
        if model_id.lower().startswith("glm-"):
            return f"z-ai/{model_id}"
        return model_id

    def list_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List available models.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            List of ModelInfo objects.
        """
        return self.provider.list_models(force_refresh=force_refresh)

    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """Get information about a specific model.

        Args:
            model_id: The model ID to look up.

        Returns:
            ModelInfo for the model, or None if not found.
        """
        return self.provider.get_model_info(model_id)

    def is_available(self) -> bool:
        """Check if the model manager is properly configured.

        Returns:
            True if the provider is available.
        """
        return self.provider.is_available()

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics.

        Returns:
            Dictionary with usage statistics.
        """
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
        }
