"""Model manager for Council MCP server."""

import logging
import os
from typing import Any, Optional

from .providers import LLMProviderError, LLMResponse, ModelInfo, OpenRouterProvider

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages LLM interactions for Council MCP server.

    This class provides a unified interface for:
    - Generating content from LLMs via OpenRouter
    - Switching between different models
    - Tracking usage statistics
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """Initialize the model manager.

        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY.
            default_model: Default model to use. If None, reads from COUNCIL_DEFAULT_MODEL
                          or defaults to "google/gemini-3-pro-preview".
            timeout: Request timeout in seconds. If None, reads from COUNCIL_TIMEOUT
                    or defaults to 600.0 (10 minutes).
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        # default_model always has a value due to the fallback
        self.default_model: str = (
            default_model
            or os.getenv("COUNCIL_DEFAULT_MODEL", "google/gemini-3-pro-preview")
            or "google/gemini-3-pro-preview"
        )
        self.timeout = timeout or float(os.getenv("COUNCIL_TIMEOUT", "600000")) / 1000

        # Initialize the provider
        self._provider: Optional[OpenRouterProvider] = None

        # Current active model (can be changed with set_model)
        self._active_model: str = self.default_model

        # Statistics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0

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
    def active_model(self) -> str:
        """Get the currently active model."""
        return self._active_model

    def set_model(self, model_id: str) -> bool:
        """Set the active model for subsequent requests.

        Args:
            model_id: The model ID to use (e.g., "google/gemini-3-pro-preview").

        Returns:
            True if the model was set successfully.
        """
        logger.info(f"Setting active model to: {model_id}")
        self._active_model = model_id
        return True

    def generate_content(
        self,
        prompt: str,
        model: Optional[str] = None,
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
            Tuple of (response_content, model_used).

        Raises:
            LLMProviderError: If generation fails.
        """
        model_to_use = model or self._active_model
        self.total_calls += 1

        try:
            response = self.provider.generate(prompt, model=model_to_use, **kwargs)
            self.successful_calls += 1
            return response.content, response.model

        except LLMProviderError as e:
            self.failed_calls += 1
            logger.error(f"Generation failed: {e}")
            raise

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
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
        model_to_use = model or self._active_model
        self.total_calls += 1

        try:
            response = self.provider.generate(prompt, model=model_to_use, **kwargs)
            self.successful_calls += 1
            return response

        except LLMProviderError as e:
            self.failed_calls += 1
            logger.error(f"Generation failed: {e}")
            raise

    def list_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List available models.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            List of ModelInfo objects.
        """
        return self.provider.list_models(force_refresh=force_refresh)

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
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
        }
