"""Tests for ModelManager."""

from unittest.mock import Mock, patch

import pytest

from council.manager import ModelManager
from council.providers.base import (
    LLMProviderError,
    LLMResponse,
    ModelInfo,
)


class TestModelManagerInit:
    """Tests for ModelManager initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        manager = ModelManager(api_key="test-key")

        assert manager.api_key == "test-key"
        assert manager.default_model == "google/gemini-3-pro-preview"
        assert manager.timeout == 600.0
        assert manager.total_calls == 0
        assert manager.successful_calls == 0
        assert manager.failed_calls == 0

    def test_init_with_custom_model(self):
        """Test initialization with custom default model."""
        manager = ModelManager(
            api_key="test-key",
            default_model="anthropic/claude-3-opus",
        )

        assert manager.default_model == "anthropic/claude-3-opus"
        assert manager.active_model == "anthropic/claude-3-opus"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        manager = ModelManager(
            api_key="test-key",
            timeout=120.0,
        )

        assert manager.timeout == 120.0

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-key"})
    def test_init_from_env(self):
        """Test initialization from environment variable."""
        manager = ModelManager()

        assert manager.api_key == "env-key"

    @patch.dict(
        "os.environ",
        {
            "COUNCIL_DEFAULT_MODEL": "openai/gpt-4",
            "COUNCIL_TIMEOUT": "300000",
        },
    )
    def test_init_from_council_env_vars(self):
        """Test initialization from COUNCIL_* environment variables."""
        manager = ModelManager(api_key="test-key")

        assert manager.default_model == "openai/gpt-4"
        assert manager.timeout == 300.0  # 300000ms / 1000


class TestModelManagerSetModel:
    """Tests for model switching."""

    def test_set_model(self):
        """Test setting active model."""
        manager = ModelManager(api_key="test-key")

        result = manager.set_model("anthropic/claude-3-opus")

        assert result is True
        assert manager.active_model == "anthropic/claude-3-opus"

    def test_set_model_multiple_times(self):
        """Test changing model multiple times."""
        manager = ModelManager(api_key="test-key")

        manager.set_model("model-1")
        assert manager.active_model == "model-1"

        manager.set_model("model-2")
        assert manager.active_model == "model-2"


class TestModelManagerGenerateContent:
    """Tests for generate_content method (backward compatible API)."""

    @pytest.fixture
    def manager(self):
        """Create a manager with mocked provider."""
        return ModelManager(api_key="test-key")

    @pytest.fixture
    def mock_response(self):
        """Create a mock LLM response."""
        return LLMResponse(
            content="Test response",
            model="google/gemini-3-pro-preview",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    @patch("council.manager.OpenRouterProvider")
    def test_generate_content_success(self, mock_provider_class, mock_response):
        """Test successful content generation."""
        mock_provider = Mock()
        mock_provider.generate.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        content, model = manager.generate_content("Hello")

        assert content == "Test response"
        assert model == "google/gemini-3-pro-preview"
        assert manager.total_calls == 1
        assert manager.successful_calls == 1
        assert manager.failed_calls == 0

    @patch("council.manager.OpenRouterProvider")
    def test_generate_content_with_model_override(self, mock_provider_class, mock_response):
        """Test content generation with model override."""
        mock_response.model = "anthropic/claude-3-opus"
        mock_provider = Mock()
        mock_provider.generate.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        content, model = manager.generate_content("Hello", model="anthropic/claude-3-opus")

        mock_provider.generate.assert_called_once()
        call_args = mock_provider.generate.call_args
        assert call_args[1]["model"] == "anthropic/claude-3-opus"

    @patch("council.manager.OpenRouterProvider")
    def test_generate_content_uses_active_model(self, mock_provider_class, mock_response):
        """Test that generate_content uses the active model."""
        mock_response.model = "openai/gpt-4"
        mock_provider = Mock()
        mock_provider.generate.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        manager.set_model("openai/gpt-4")
        manager.generate_content("Hello")

        call_args = mock_provider.generate.call_args
        assert call_args[1]["model"] == "openai/gpt-4"

    @patch("council.manager.OpenRouterProvider")
    def test_generate_content_failure(self, mock_provider_class):
        """Test failed content generation."""
        mock_provider = Mock()
        mock_provider.generate.side_effect = LLMProviderError("API Error")
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")

        with pytest.raises(LLMProviderError):
            manager.generate_content("Hello")

        assert manager.total_calls == 1
        assert manager.successful_calls == 0
        assert manager.failed_calls == 1


class TestModelManagerGenerate:
    """Tests for generate method (returns full response)."""

    @pytest.fixture
    def mock_response(self):
        """Create a mock LLM response."""
        return LLMResponse(
            content="Test response",
            model="google/gemini-3-pro-preview",
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            metadata={"id": "test-123"},
        )

    @patch("council.manager.OpenRouterProvider")
    def test_generate_returns_full_response(self, mock_provider_class, mock_response):
        """Test that generate returns the full LLMResponse object."""
        mock_provider = Mock()
        mock_provider.generate.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        response = manager.generate("Hello")

        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.model == "google/gemini-3-pro-preview"
        assert response.usage["total_tokens"] == 30
        assert response.metadata["id"] == "test-123"


class TestModelManagerListModels:
    """Tests for list_models method."""

    @patch("council.manager.OpenRouterProvider")
    def test_list_models(self, mock_provider_class):
        """Test listing models."""
        mock_models = [
            ModelInfo(id="google/gemini-3-pro-preview", name="Gemini 2.5 Pro", provider="google"),
            ModelInfo(id="anthropic/claude-3-opus", name="Claude 3 Opus", provider="anthropic"),
        ]
        mock_provider = Mock()
        mock_provider.list_models.return_value = mock_models
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        models = manager.list_models()

        assert len(models) == 2
        assert models[0].id == "google/gemini-3-pro-preview"

    @patch("council.manager.OpenRouterProvider")
    def test_list_models_force_refresh(self, mock_provider_class):
        """Test force refresh on list_models."""
        mock_provider = Mock()
        mock_provider.list_models.return_value = []
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        manager.list_models(force_refresh=True)

        mock_provider.list_models.assert_called_once_with(force_refresh=True)


class TestModelManagerGetModelInfo:
    """Tests for get_model_info method."""

    @patch("council.manager.OpenRouterProvider")
    def test_get_model_info_found(self, mock_provider_class):
        """Test getting info for existing model."""
        mock_info = ModelInfo(
            id="google/gemini-3-pro-preview",
            name="Gemini 2.5 Pro",
            provider="google",
        )
        mock_provider = Mock()
        mock_provider.get_model_info.return_value = mock_info
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        info = manager.get_model_info("google/gemini-3-pro-preview")

        assert info is not None
        assert info.id == "google/gemini-3-pro-preview"

    @patch("council.manager.OpenRouterProvider")
    def test_get_model_info_not_found(self, mock_provider_class):
        """Test getting info for non-existent model."""
        mock_provider = Mock()
        mock_provider.get_model_info.return_value = None
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        info = manager.get_model_info("nonexistent/model")

        assert info is None


class TestModelManagerIsAvailable:
    """Tests for is_available method."""

    @patch("council.manager.OpenRouterProvider")
    def test_is_available_true(self, mock_provider_class):
        """Test is_available returns True when provider is available."""
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        assert manager.is_available() is True

    @patch("council.manager.OpenRouterProvider")
    def test_is_available_false(self, mock_provider_class):
        """Test is_available returns False when provider is unavailable."""
        mock_provider = Mock()
        mock_provider.is_available.return_value = False
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        assert manager.is_available() is False


class TestModelManagerStats:
    """Tests for get_stats method."""

    @patch("council.manager.OpenRouterProvider")
    def test_get_stats_initial(self, mock_provider_class):
        """Test initial stats."""
        manager = ModelManager(api_key="test-key")
        stats = manager.get_stats()

        assert stats["provider"] == "openrouter"
        assert stats["active_model"] == "google/gemini-3-pro-preview"
        assert stats["default_model"] == "google/gemini-3-pro-preview"
        assert stats["total_calls"] == 0
        assert stats["successful_calls"] == 0
        assert stats["failed_calls"] == 0
        assert stats["success_rate"] == "0.0%"

    @patch("council.manager.OpenRouterProvider")
    def test_get_stats_after_calls(self, mock_provider_class):
        """Test stats after making calls."""
        mock_response = LLMResponse(content="Test", model="test")
        mock_provider = Mock()
        mock_provider.generate.return_value = mock_response
        mock_provider_class.return_value = mock_provider

        manager = ModelManager(api_key="test-key")
        manager.generate_content("Test 1")
        manager.generate_content("Test 2")

        stats = manager.get_stats()
        assert stats["total_calls"] == 2
        assert stats["successful_calls"] == 2
        assert stats["success_rate"] == "100.0%"
