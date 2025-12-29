"""Tests for OpenRouter LLM provider."""

from unittest.mock import Mock, patch

import httpx
import pytest

from council.providers.base import (
    AuthenticationError,
    LLMProviderError,
    LLMResponse,
    ModelInfo,
    ModelNotFoundError,
    RateLimitError,
)
from council.providers.openrouter import OPENROUTER_BASE_URL, OpenRouterProvider


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_from_openrouter_basic(self):
        """Test creating ModelInfo from OpenRouter API response."""
        data = {
            "id": "google/gemini-3-pro-preview",
            "name": "Gemini 2.5 Pro",
            "context_length": 1000000,
            "pricing": {"prompt": 0.001, "completion": 0.002},
        }
        info = ModelInfo.from_openrouter(data)

        assert info.id == "google/gemini-3-pro-preview"
        assert info.name == "Gemini 2.5 Pro"
        assert info.provider == "google"
        assert info.context_length == 1000000
        assert info.pricing == {"prompt": 0.001, "completion": 0.002}
        assert info.is_free is False

    def test_from_openrouter_free_model(self):
        """Test detecting free tier models."""
        data = {
            "id": "google/gemini-2.5-flash:free",
            "name": "Gemini 2.5 Flash (free)",
        }
        info = ModelInfo.from_openrouter(data)

        assert info.is_free is True
        assert info.provider == "google"

    def test_from_openrouter_with_vision(self):
        """Test detecting vision capability."""
        data = {
            "id": "openai/gpt-4-vision",
            "name": "GPT-4 Vision",
            "architecture": {"modality": "text+image->text"},
        }
        info = ModelInfo.from_openrouter(data)

        assert "vision" in info.capabilities

    def test_from_openrouter_with_code(self):
        """Test detecting code capability from description."""
        data = {
            "id": "anthropic/claude-3-opus",
            "name": "Claude 3 Opus",
            "description": "Advanced reasoning and code generation",
        }
        info = ModelInfo.from_openrouter(data)

        assert "code" in info.capabilities

    def test_from_openrouter_no_provider_slash(self):
        """Test handling model ID without provider prefix."""
        data = {
            "id": "standalone-model",
            "name": "Standalone Model",
        }
        info = ModelInfo.from_openrouter(data)

        assert info.provider == "unknown"


class TestOpenRouterProviderInit:
    """Tests for OpenRouterProvider initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        provider = OpenRouterProvider(api_key="test-key")

        assert provider.api_key == "test-key"
        assert provider.default_model == "google/gemini-3-pro-preview"
        assert provider.timeout == 600.0
        assert provider.name == "openrouter"

    def test_init_with_custom_model(self):
        """Test initialization with custom default model."""
        provider = OpenRouterProvider(
            api_key="test-key",
            default_model="anthropic/claude-3-opus",
        )

        assert provider.default_model == "anthropic/claude-3-opus"

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        provider = OpenRouterProvider(
            api_key="test-key",
            timeout=120.0,
        )

        assert provider.timeout == 120.0

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "env-key"})
    def test_init_from_env(self):
        """Test initialization from environment variable."""
        provider = OpenRouterProvider()

        assert provider.api_key == "env-key"

    def test_is_available_with_key(self):
        """Test is_available returns True when API key is set."""
        provider = OpenRouterProvider(api_key="test-key")

        assert provider.is_available() is True

    def test_is_available_without_key(self):
        """Test is_available returns False when API key is not set."""
        provider = OpenRouterProvider(api_key=None)
        provider.api_key = None  # Ensure no env var fallback

        assert provider.is_available() is False


class TestOpenRouterProviderClient:
    """Tests for OpenRouter client initialization."""

    def test_client_lazy_initialization(self):
        """Test that client is lazily initialized."""
        provider = OpenRouterProvider(api_key="test-key")

        assert provider._client is None

    @patch("council.providers.openrouter.OpenAI")
    def test_client_created_on_access(self, mock_openai):
        """Test that client is created on first access."""
        provider = OpenRouterProvider(api_key="test-key")
        _ = provider.client

        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["base_url"] == OPENROUTER_BASE_URL
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["timeout"] == 600.0

    def test_client_raises_auth_error_without_key(self):
        """Test that accessing client without API key raises AuthenticationError."""
        provider = OpenRouterProvider(api_key=None)
        provider.api_key = None

        with pytest.raises(AuthenticationError) as exc_info:
            _ = provider.client

        assert "API key not configured" in str(exc_info.value)
        assert exc_info.value.provider == "openrouter"


class TestOpenRouterProviderGenerate:
    """Tests for OpenRouterProvider.generate()."""

    @pytest.fixture
    def provider(self):
        """Create a provider with mocked client."""
        provider = OpenRouterProvider(api_key="test-key")
        return provider

    @pytest.fixture
    def mock_completion(self):
        """Create a mock completion response."""
        mock = Mock()
        mock.id = "chatcmpl-123"
        mock.created = 1700000000
        mock.choices = [Mock(message=Mock(content="Test response"))]
        mock.usage = Mock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        return mock

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_success(self, mock_openai_class, mock_completion):
        """Test successful generation."""
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")
        response = provider.generate("Hello")

        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.model == "google/gemini-3-pro-preview"
        assert response.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
        assert response.metadata["id"] == "chatcmpl-123"

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_with_custom_model(self, mock_openai_class, mock_completion):
        """Test generation with custom model override."""
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")
        response = provider.generate("Hello", model="anthropic/claude-3-opus")

        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["model"] == "anthropic/claude-3-opus"
        assert response.model == "anthropic/claude-3-opus"

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_with_parameters(self, mock_openai_class, mock_completion):
        """Test generation with custom parameters."""
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")
        provider.generate(
            "Hello",
            temperature=0.5,
            max_tokens=100,
        )

        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.5
        assert call_args[1]["max_tokens"] == 100

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_rate_limit_error(self, mock_openai_class):
        """Test rate limit error handling."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Error code: 429 - Rate limit exceeded"
        )
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")

        with pytest.raises(RateLimitError) as exc_info:
            provider.generate("Hello")

        assert exc_info.value.is_retryable is True
        assert exc_info.value.provider == "openrouter"

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_auth_error(self, mock_openai_class):
        """Test authentication error handling."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Error code: 401 - Invalid API key"
        )
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")

        with pytest.raises(AuthenticationError) as exc_info:
            provider.generate("Hello")

        assert exc_info.value.is_retryable is False
        assert exc_info.value.provider == "openrouter"

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_model_not_found_error(self, mock_openai_class):
        """Test model not found error handling."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Error code: 404 - Model not found"
        )
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")

        with pytest.raises(ModelNotFoundError) as exc_info:
            provider.generate("Hello", model="nonexistent/model")

        assert exc_info.value.is_retryable is False
        assert exc_info.value.model == "nonexistent/model"

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_timeout_error_is_retryable(self, mock_openai_class):
        """Test timeout errors are marked as retryable."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("Connection timeout")
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Hello")

        assert exc_info.value.is_retryable is True

    @patch("council.providers.openrouter.OpenAI")
    def test_generate_empty_response(self, mock_openai_class):
        """Test handling of empty response content."""
        mock_completion = Mock()
        mock_completion.id = "chatcmpl-123"
        mock_completion.created = 1700000000
        mock_completion.choices = [Mock(message=Mock(content=None))]
        mock_completion.usage = None

        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_class.return_value = mock_client

        provider = OpenRouterProvider(api_key="test-key")
        response = provider.generate("Hello")

        assert response.content == ""
        assert response.usage == {}


class TestOpenRouterProviderListModels:
    """Tests for OpenRouterProvider.list_models()."""

    @pytest.fixture
    def mock_models_response(self):
        """Create a mock models API response."""
        return {
            "data": [
                {
                    "id": "google/gemini-3-pro-preview",
                    "name": "Gemini 2.5 Pro",
                    "context_length": 1000000,
                    "pricing": {"prompt": 0.001, "completion": 0.002},
                },
                {
                    "id": "anthropic/claude-3-opus",
                    "name": "Claude 3 Opus",
                    "context_length": 200000,
                    "pricing": {"prompt": 0.015, "completion": 0.075},
                },
            ]
        }

    @patch("council.providers.openrouter.httpx.get")
    def test_list_models_success(self, mock_get, mock_models_response):
        """Test successful model listing."""
        mock_response = Mock()
        mock_response.json.return_value = mock_models_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")
        models = provider.list_models()

        assert len(models) == 2
        assert models[0].id == "google/gemini-3-pro-preview"
        assert models[1].id == "anthropic/claude-3-opus"

    @patch("council.providers.openrouter.httpx.get")
    def test_list_models_caching(self, mock_get, mock_models_response):
        """Test that models are cached after first fetch."""
        mock_response = Mock()
        mock_response.json.return_value = mock_models_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")

        # First call should fetch
        models1 = provider.list_models()
        # Second call should use cache
        models2 = provider.list_models()

        assert mock_get.call_count == 1
        assert models1 == models2

    @patch("council.providers.openrouter.httpx.get")
    def test_list_models_force_refresh(self, mock_get, mock_models_response):
        """Test force_refresh bypasses cache."""
        mock_response = Mock()
        mock_response.json.return_value = mock_models_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")

        # First call
        provider.list_models()
        # Force refresh
        provider.list_models(force_refresh=True)

        assert mock_get.call_count == 2

    @patch("council.providers.openrouter.httpx.get")
    def test_list_models_error_returns_empty(self, mock_get):
        """Test that errors return empty list when no cache."""
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        provider = OpenRouterProvider(api_key="test-key")
        models = provider.list_models()

        assert models == []

    @patch("council.providers.openrouter.httpx.get")
    def test_list_models_error_returns_cached(self, mock_get, mock_models_response):
        """Test that errors return cached data when available."""
        mock_response = Mock()
        mock_response.json.return_value = mock_models_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")

        # First call populates cache
        models1 = provider.list_models()

        # Make next call fail
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        # Force refresh should fail but return cached data
        models2 = provider.list_models(force_refresh=True)

        assert len(models2) == 2
        assert models1 == models2


class TestOpenRouterProviderGetModelInfo:
    """Tests for OpenRouterProvider.get_model_info()."""

    @patch("council.providers.openrouter.httpx.get")
    def test_get_model_info_found(self, mock_get):
        """Test getting info for an existing model."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"id": "google/gemini-3-pro-preview", "name": "Gemini 2.5 Pro"},
                {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")
        info = provider.get_model_info("google/gemini-3-pro-preview")

        assert info is not None
        assert info.id == "google/gemini-3-pro-preview"
        assert info.name == "Gemini 2.5 Pro"

    @patch("council.providers.openrouter.httpx.get")
    def test_get_model_info_not_found(self, mock_get):
        """Test getting info for a non-existent model."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = OpenRouterProvider(api_key="test-key")
        info = provider.get_model_info("nonexistent/model")

        assert info is None
