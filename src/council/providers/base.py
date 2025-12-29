"""Base classes for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Information about an available model."""

    id: str
    name: str
    provider: str
    context_length: int = 0
    pricing: dict[str, float] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    is_free: bool = False

    @classmethod
    def from_openrouter(cls, data: dict[str, Any]) -> "ModelInfo":
        """Create ModelInfo from OpenRouter API response."""
        model_id = data.get("id", "")
        # Extract provider from model ID (e.g., "google/gemini-3-pro-preview" -> "google")
        provider = model_id.split("/")[0] if "/" in model_id else "unknown"

        # Check if it's a free model (ends with ":free")
        is_free = model_id.endswith(":free")

        # Extract capabilities from architecture or description
        capabilities = []
        arch = data.get("architecture", {})
        if arch.get("modality") == "text+image->text":
            capabilities.append("vision")
        if "function" in str(data.get("description", "")).lower():
            capabilities.append("function_calling")
        if "code" in str(data.get("description", "")).lower():
            capabilities.append("code")

        return cls(
            id=model_id,
            name=data.get("name", model_id),
            provider=provider,
            context_length=data.get("context_length", 0),
            pricing={
                "prompt": data.get("pricing", {}).get("prompt", 0),
                "completion": data.get("pricing", {}).get("completion", 0),
            },
            capabilities=capabilities,
            is_free=is_free,
        )


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the model.
            model: The model to use. If None, uses the default model.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse containing the generated content and metadata.

        Raises:
            LLMProviderError: If the generation fails.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """List available models from this provider.

        Returns:
            List of ModelInfo objects describing available models.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured.

        Returns:
            True if the provider can be used, False otherwise.
        """
        ...


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(
        self,
        message: str,
        provider: str = "",
        model: str = "",
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.is_retryable = is_retryable


class RateLimitError(LLMProviderError):
    """Raised when rate limited by the provider."""

    def __init__(self, message: str, provider: str = "", model: str = ""):
        super().__init__(message, provider, model, is_retryable=True)


class AuthenticationError(LLMProviderError):
    """Raised when authentication fails."""

    def __init__(self, message: str, provider: str = "", model: str = ""):
        super().__init__(message, provider, model, is_retryable=False)


class ModelNotFoundError(LLMProviderError):
    """Raised when the requested model is not found."""

    def __init__(self, message: str, provider: str = "", model: str = ""):
        super().__init__(message, provider, model, is_retryable=False)
