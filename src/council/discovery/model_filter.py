"""Model filtering for Council MCP server."""

import logging
from typing import Optional

from council.providers.base import ModelInfo

logger = logging.getLogger(__name__)


class ModelFilter:
    """Filter models by various criteria.

    This class provides methods to filter models by:
    - Provider (google, anthropic, openai, etc.)
    - Capability (vision, code, function_calling, reasoning)
    - Free tier availability
    - Text search on name/description
    - Context length
    """

    def __init__(self, models: list[ModelInfo]):
        """Initialize the filter with a list of models.

        Args:
            models: List of ModelInfo objects to filter.
        """
        self.models = models

    def by_provider(self, provider: str) -> "ModelFilter":
        """Filter models by provider.

        Args:
            provider: Provider name (e.g., "google", "anthropic", "openai").

        Returns:
            New ModelFilter with filtered models.
        """
        filtered = [m for m in self.models if m.provider.lower() == provider.lower()]
        return ModelFilter(filtered)

    def by_capability(self, capability: str) -> "ModelFilter":
        """Filter models by capability.

        Args:
            capability: Capability name (e.g., "vision", "code", "function_calling").

        Returns:
            New ModelFilter with filtered models.
        """
        filtered = [
            m for m in self.models if capability.lower() in [c.lower() for c in m.capabilities]
        ]
        return ModelFilter(filtered)

    def free_only(self) -> "ModelFilter":
        """Filter to only include free tier models.

        Returns:
            New ModelFilter with only free models.
        """
        filtered = [m for m in self.models if m.is_free]
        return ModelFilter(filtered)

    def paid_only(self) -> "ModelFilter":
        """Filter to only include paid models.

        Returns:
            New ModelFilter with only paid models.
        """
        filtered = [m for m in self.models if not m.is_free]
        return ModelFilter(filtered)

    def search(self, query: str) -> "ModelFilter":
        """Search models by name or ID.

        Args:
            query: Search query to match against name or ID.

        Returns:
            New ModelFilter with matching models.
        """
        query_lower = query.lower()
        filtered = [
            m for m in self.models if query_lower in m.name.lower() or query_lower in m.id.lower()
        ]
        return ModelFilter(filtered)

    def min_context_length(self, length: int) -> "ModelFilter":
        """Filter models with at least the specified context length.

        Args:
            length: Minimum context length in tokens.

        Returns:
            New ModelFilter with models meeting the requirement.
        """
        filtered = [m for m in self.models if m.context_length >= length]
        return ModelFilter(filtered)

    def limit(self, count: int) -> "ModelFilter":
        """Limit the number of models returned.

        Args:
            count: Maximum number of models to return.

        Returns:
            New ModelFilter with limited models.
        """
        return ModelFilter(self.models[:count])

    def sort_by_context_length(self, descending: bool = True) -> "ModelFilter":
        """Sort models by context length.

        Args:
            descending: If True, sort from highest to lowest.

        Returns:
            New ModelFilter with sorted models.
        """
        sorted_models = sorted(
            self.models,
            key=lambda m: m.context_length,
            reverse=descending,
        )
        return ModelFilter(sorted_models)

    def sort_by_name(self, descending: bool = False) -> "ModelFilter":
        """Sort models by name.

        Args:
            descending: If True, sort in reverse order.

        Returns:
            New ModelFilter with sorted models.
        """
        sorted_models = sorted(
            self.models,
            key=lambda m: m.name.lower(),
            reverse=descending,
        )
        return ModelFilter(sorted_models)

    def to_list(self) -> list[ModelInfo]:
        """Get the filtered models as a list.

        Returns:
            List of ModelInfo objects.
        """
        return list(self.models)

    def count(self) -> int:
        """Get the count of filtered models.

        Returns:
            Number of models.
        """
        return len(self.models)

    def first(self) -> Optional[ModelInfo]:
        """Get the first model in the filtered list.

        Returns:
            First ModelInfo or None if empty.
        """
        return self.models[0] if self.models else None

    @classmethod
    def apply_filters(
        cls,
        models: list[ModelInfo],
        provider: Optional[str] = None,
        capability: Optional[str] = None,
        free_only: bool = False,
        search: Optional[str] = None,
        min_context: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[ModelInfo]:
        """Apply multiple filters at once.

        This is a convenience method that applies all specified filters.

        Args:
            models: List of models to filter.
            provider: Filter by provider name.
            capability: Filter by capability.
            free_only: If True, only include free models.
            search: Search query for name/ID.
            min_context: Minimum context length.
            limit: Maximum number of results.

        Returns:
            Filtered list of ModelInfo objects.
        """
        result = cls(models)

        if provider:
            result = result.by_provider(provider)
        if capability:
            result = result.by_capability(capability)
        if free_only:
            result = result.free_only()
        if search:
            result = result.search(search)
        if min_context:
            result = result.min_context_length(min_context)
        if limit:
            result = result.limit(limit)

        return result.to_list()
