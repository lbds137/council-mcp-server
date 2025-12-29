"""Tests for model discovery module."""

import time
from unittest.mock import Mock, patch

import pytest

from council.discovery.model_cache import ModelCache
from council.discovery.model_filter import ModelFilter
from council.providers.base import ModelInfo


class TestModelCache:
    """Tests for ModelCache class."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        cache = ModelCache(api_key="test-key")

        assert cache.api_key == "test-key"
        assert cache.ttl_seconds == 3600.0
        assert cache.timeout == 30.0
        assert cache._models == []
        assert cache._last_fetch == 0

    def test_init_custom_ttl(self):
        """Test initialization with custom TTL."""
        cache = ModelCache(api_key="test-key", ttl_seconds=600.0)

        assert cache.ttl_seconds == 600.0

    def test_is_expired_empty_cache(self):
        """Test is_expired returns True for empty cache."""
        cache = ModelCache(api_key="test-key")

        assert cache.is_expired is True

    def test_is_expired_fresh_cache(self):
        """Test is_expired returns False for fresh cache."""
        cache = ModelCache(api_key="test-key", ttl_seconds=3600)
        cache._models = [Mock()]
        cache._last_fetch = time.time()

        assert cache.is_expired is False

    def test_is_expired_old_cache(self):
        """Test is_expired returns True for expired cache."""
        cache = ModelCache(api_key="test-key", ttl_seconds=60)
        cache._models = [Mock()]
        cache._last_fetch = time.time() - 120  # 2 minutes ago

        assert cache.is_expired is True

    def test_age_seconds_no_fetch(self):
        """Test age_seconds returns infinity when never fetched."""
        cache = ModelCache(api_key="test-key")

        assert cache.age_seconds == float("inf")

    def test_age_seconds_after_fetch(self):
        """Test age_seconds returns correct value."""
        cache = ModelCache(api_key="test-key")
        cache._last_fetch = time.time() - 60

        assert 59 <= cache.age_seconds <= 61

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_models_fetches_on_empty(self, mock_get):
        """Test get_models fetches when cache is empty."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [{"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"}]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key")
        models = cache.get_models()

        assert len(models) == 1
        assert models[0].id == "google/gemini-2.5-pro"
        mock_get.assert_called_once()

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_models_uses_cache(self, mock_get):
        """Test get_models uses cache when not expired."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": "test", "name": "Test"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key", ttl_seconds=3600)

        # First call fetches
        cache.get_models()
        # Second call should use cache
        cache.get_models()

        assert mock_get.call_count == 1

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_models_force_refresh(self, mock_get):
        """Test get_models with force_refresh bypasses cache."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": "test", "name": "Test"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key", ttl_seconds=3600)

        cache.get_models()
        cache.get_models(force_refresh=True)

        assert mock_get.call_count == 2

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_model_by_id(self, mock_get):
        """Test get_model returns correct model."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"id": "model-1", "name": "Model 1"},
                {"id": "model-2", "name": "Model 2"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key")
        model = cache.get_model("model-2")

        assert model is not None
        assert model.id == "model-2"

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_model_not_found(self, mock_get):
        """Test get_model returns None for unknown model."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": "test", "name": "Test"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key")
        model = cache.get_model("nonexistent")

        assert model is None

    def test_clear(self):
        """Test clear empties the cache."""
        cache = ModelCache(api_key="test-key")
        cache._models = [Mock()]
        cache._last_fetch = time.time()

        cache.clear()

        assert cache._models == []
        assert cache._last_fetch == 0

    @patch("council.discovery.model_cache.httpx.get")
    def test_get_stats(self, mock_get):
        """Test get_stats returns correct statistics."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": "test", "name": "Test"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        cache = ModelCache(api_key="test-key", ttl_seconds=3600)
        cache.get_models()

        stats = cache.get_stats()

        assert stats["cached_models"] == 1
        assert stats["ttl_seconds"] == 3600
        assert stats["fetch_count"] == 1
        assert stats["is_expired"] is False


class TestModelFilter:
    """Tests for ModelFilter class."""

    @pytest.fixture
    def sample_models(self):
        """Create sample models for testing."""
        return [
            ModelInfo(
                id="google/gemini-2.5-pro",
                name="Gemini 2.5 Pro",
                provider="google",
                context_length=1000000,
                capabilities=["code", "vision"],
                is_free=False,
            ),
            ModelInfo(
                id="google/gemini-2.5-flash:free",
                name="Gemini 2.5 Flash (free)",
                provider="google",
                context_length=500000,
                capabilities=["code"],
                is_free=True,
            ),
            ModelInfo(
                id="anthropic/claude-3-opus",
                name="Claude 3 Opus",
                provider="anthropic",
                context_length=200000,
                capabilities=["code", "vision", "function_calling"],
                is_free=False,
            ),
            ModelInfo(
                id="openai/gpt-4-turbo",
                name="GPT-4 Turbo",
                provider="openai",
                context_length=128000,
                capabilities=["function_calling"],
                is_free=False,
            ),
        ]

    def test_by_provider(self, sample_models):
        """Test filtering by provider."""
        filter = ModelFilter(sample_models)
        result = filter.by_provider("google").to_list()

        assert len(result) == 2
        assert all(m.provider == "google" for m in result)

    def test_by_capability(self, sample_models):
        """Test filtering by capability."""
        filter = ModelFilter(sample_models)
        result = filter.by_capability("vision").to_list()

        assert len(result) == 2
        assert all("vision" in m.capabilities for m in result)

    def test_free_only(self, sample_models):
        """Test filtering for free models only."""
        filter = ModelFilter(sample_models)
        result = filter.free_only().to_list()

        assert len(result) == 1
        assert result[0].is_free is True

    def test_paid_only(self, sample_models):
        """Test filtering for paid models only."""
        filter = ModelFilter(sample_models)
        result = filter.paid_only().to_list()

        assert len(result) == 3
        assert all(not m.is_free for m in result)

    def test_search(self, sample_models):
        """Test searching by name."""
        filter = ModelFilter(sample_models)
        result = filter.search("claude").to_list()

        assert len(result) == 1
        assert result[0].id == "anthropic/claude-3-opus"

    def test_search_by_id(self, sample_models):
        """Test searching by model ID."""
        filter = ModelFilter(sample_models)
        result = filter.search("gpt-4").to_list()

        assert len(result) == 1
        assert result[0].id == "openai/gpt-4-turbo"

    def test_min_context_length(self, sample_models):
        """Test filtering by minimum context length."""
        filter = ModelFilter(sample_models)
        result = filter.min_context_length(500000).to_list()

        assert len(result) == 2
        assert all(m.context_length >= 500000 for m in result)

    def test_limit(self, sample_models):
        """Test limiting results."""
        filter = ModelFilter(sample_models)
        result = filter.limit(2).to_list()

        assert len(result) == 2

    def test_sort_by_context_length(self, sample_models):
        """Test sorting by context length."""
        filter = ModelFilter(sample_models)
        result = filter.sort_by_context_length().to_list()

        assert result[0].context_length == 1000000  # Highest first
        assert result[-1].context_length == 128000  # Lowest last

    def test_sort_by_name(self, sample_models):
        """Test sorting by name."""
        filter = ModelFilter(sample_models)
        result = filter.sort_by_name().to_list()

        names = [m.name for m in result]
        assert names == sorted(names, key=str.lower)

    def test_chained_filters(self, sample_models):
        """Test chaining multiple filters."""
        filter = ModelFilter(sample_models)
        result = filter.by_provider("google").by_capability("code").to_list()

        assert len(result) == 2
        assert all(m.provider == "google" for m in result)

    def test_count(self, sample_models):
        """Test count method."""
        filter = ModelFilter(sample_models)
        assert filter.count() == 4
        assert filter.by_provider("google").count() == 2

    def test_first(self, sample_models):
        """Test first method."""
        filter = ModelFilter(sample_models)
        first = filter.first()

        assert first is not None
        assert first.id == "google/gemini-2.5-pro"

    def test_first_empty(self):
        """Test first on empty filter."""
        filter = ModelFilter([])
        assert filter.first() is None

    def test_apply_filters(self, sample_models):
        """Test apply_filters convenience method."""
        result = ModelFilter.apply_filters(
            sample_models,
            provider="google",
            capability="code",
            limit=1,
        )

        assert len(result) == 1
        assert result[0].provider == "google"
