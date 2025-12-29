"""Model caching with TTL for Council MCP server."""

import logging
import os
import time
from typing import Optional

import httpx

from council.providers.base import ModelInfo

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


class ModelCache:
    """Cache for OpenRouter model information with TTL.

    This class provides:
    - In-memory caching of model information
    - Configurable TTL (time-to-live)
    - Automatic refresh when cache expires
    - Thread-safe access (through atomic operations)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        ttl_seconds: float = 3600.0,  # 1 hour default
        timeout: float = 30.0,
    ):
        """Initialize the model cache.

        Args:
            api_key: OpenRouter API key. If None, reads from OPENROUTER_API_KEY.
            ttl_seconds: Cache TTL in seconds. Default is 1 hour.
            timeout: Request timeout in seconds for fetching models.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.ttl_seconds = ttl_seconds or float(os.getenv("COUNCIL_CACHE_TTL", "3600"))
        self.timeout = timeout

        self._models: list[ModelInfo] = []
        self._last_fetch: float = 0
        self._fetch_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if the cache has expired."""
        if not self._models:
            return True
        return time.time() - self._last_fetch > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get the age of the cache in seconds."""
        if self._last_fetch == 0:
            return float("inf")
        return time.time() - self._last_fetch

    def get_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """Get cached models, fetching if expired or forced.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            List of ModelInfo objects.
        """
        if force_refresh or self.is_expired:
            self._fetch_models()
        return self._models

    def _fetch_models(self) -> None:
        """Fetch models from OpenRouter API."""
        if not self.api_key:
            logger.warning("No API key configured, cannot fetch models")
            return

        logger.info("Fetching models from OpenRouter")
        try:
            response = httpx.get(
                OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            self._models = [ModelInfo.from_openrouter(m) for m in data.get("data", [])]
            self._last_fetch = time.time()
            self._fetch_count += 1

            logger.info(f"Cached {len(self._models)} models from OpenRouter")

        except Exception as e:
            logger.error(f"Failed to fetch models from OpenRouter: {e}")
            # Keep existing cache on failure

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get a specific model by ID.

        Args:
            model_id: The model ID to look up.

        Returns:
            ModelInfo if found, None otherwise.
        """
        models = self.get_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    def clear(self) -> None:
        """Clear the cache."""
        self._models = []
        self._last_fetch = 0
        logger.info("Model cache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        return {
            "cached_models": len(self._models),
            "last_fetch": self._last_fetch,
            "age_seconds": self.age_seconds if self._last_fetch > 0 else None,
            "is_expired": self.is_expired,
            "ttl_seconds": self.ttl_seconds,
            "fetch_count": self._fetch_count,
        }
