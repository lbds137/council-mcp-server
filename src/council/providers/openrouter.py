"""OpenRouter LLM provider implementation."""

import logging
import os
import time
from typing import Any, Optional

import httpx
from openai import OpenAI

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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
FAILED_FETCH_RETRY_SECONDS = 300.0


class OpenRouterProvider(LLMProvider):
    """LLM provider using OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "~openai/gpt-sol-latest",
        timeout: float = 600.0,
        app_name: str = "council-mcp",
        cache_ttl: Optional[float] = None,
    ):
        """Initialize the OpenRouter provider.

        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY env var.
            default_model: Default model to use for generation.
            timeout: Request timeout in seconds.
            app_name: Application name for OpenRouter headers.
            cache_ttl: How long to trust the model list, in seconds. If None,
                reads COUNCIL_CACHE_TTL (default 1 hour).
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.default_model = default_model
        self.timeout = timeout
        self.app_name = app_name
        self._client: Optional[OpenAI] = None
        self.cache_ttl = (
            cache_ttl if cache_ttl is not None else float(os.getenv("COUNCIL_CACHE_TTL", "3600"))
        )
        self._models_cache: Optional[list[ModelInfo]] = None
        self._next_fetch: float = 0.0

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "openrouter"

    @property
    def client(self) -> OpenAI:
        """Get or create the OpenAI client configured for OpenRouter."""
        if self._client is None:
            if not self.api_key:
                raise AuthenticationError(
                    "OpenRouter API key not configured. "
                    "Set OPENROUTER_API_KEY environment variable.",
                    provider=self.name,
                )
            self._client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout,
                default_headers={
                    "HTTP-Referer": f"https://github.com/lbds137/{self.app_name}",
                    "X-Title": self.app_name,
                },
            )
        return self._client

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response using OpenRouter.

        Args:
            prompt: The prompt to send to the model.
            model: The model to use. If None, uses the default model.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters passed to the API.

        Returns:
            LLMResponse containing the generated content and metadata.

        Raises:
            LLMProviderError: If the generation fails.
        """
        model_id = model or self.default_model
        logger.info(f"Generating with OpenRouter model: {model_id}")

        try:
            response = self.client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            content = response.choices[0].message.content or ""
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            # OpenRouter reports the model that actually ran, which differs from
            # the request when the request names a "~" alias
            served_model = response.model or model_id
            logger.info(f"OpenRouter response received from {served_model}")
            return LLMResponse(
                content=content,
                model=served_model,
                usage=usage,
                metadata={"id": response.id, "created": response.created},
            )

        except Exception as e:
            raise self._classify_error(e, model_id) from e

    def _classify_error(self, error: Exception, model_id: str) -> LLMProviderError:
        """Map an API error to a provider error, by HTTP status when there is one."""
        error_msg = str(error)
        logger.error(f"OpenRouter error: {error_msg}")
        status = getattr(error, "status_code", None)
        lowered = error_msg.lower()

        if status == 429 or (status is None and "rate limit" in lowered):
            return RateLimitError(error_msg, provider=self.name, model=model_id)
        if status in (401, 403):
            return AuthenticationError(error_msg, provider=self.name, model=model_id)
        if status == 404:
            return ModelNotFoundError(error_msg, provider=self.name, model=model_id)
        return LLMProviderError(
            error_msg,
            provider=self.name,
            model=model_id,
            is_retryable="timeout" in lowered or "timed out" in lowered,
        )

    def list_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List available models from OpenRouter, refreshed once per cache TTL.

        Args:
            force_refresh: If True, bypass the cache and fetch fresh data.

        Returns:
            List of ModelInfo objects describing available models.

        Raises:
            LLMProviderError: If the list can't be fetched and none was fetched
                before. With an earlier list on hand, that list is returned.
        """
        if self._models_cache is not None and not force_refresh and time.time() < self._next_fetch:
            return self._models_cache

        logger.info("Fetching models from OpenRouter")
        try:
            response = httpx.get(
                OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            models = [ModelInfo.from_openrouter(m) for m in data.get("data", [])]
        except Exception as e:
            logger.error(f"Failed to fetch models from OpenRouter: {e}")
            if self._models_cache is None:
                raise LLMProviderError(
                    f"Could not fetch the OpenRouter model list: {e}", provider=self.name
                ) from e
            # Keep serving the last list, and try again in a few minutes
            self._next_fetch = time.time() + FAILED_FETCH_RETRY_SECONDS
            return self._models_cache

        self._models_cache = models
        self._next_fetch = time.time() + self.cache_ttl
        logger.info(f"Fetched {len(models)} models from OpenRouter")
        return models

    def is_available(self) -> bool:
        """Check if the OpenRouter provider is available.

        Returns:
            True if the API key is configured, False otherwise.
        """
        return bool(self.api_key)

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get information about a specific model.

        Args:
            model_id: The model ID to look up.

        Returns:
            ModelInfo for the model, or None if not found or the list is unavailable.
        """
        try:
            models = self.list_models()
        except LLMProviderError:
            return None
        for model in models:
            if model.id == model_id:
                return model
        return None
