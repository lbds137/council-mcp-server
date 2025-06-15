"""
Tests for the DualModelManager class.
"""

import os
from concurrent.futures import TimeoutError as FutureTimeoutError
from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as google_exceptions

from gemini_mcp.models.manager import DualModelManager


class TestDualModelManager:
    """Test the DualModelManager class."""

    @patch("gemini_mcp.models.manager.genai")
    @patch.dict(os.environ, {}, clear=True)  # Clear env vars to test defaults
    def test_init_with_defaults(self, mock_genai):
        """Test initialization with default model names."""
        manager = DualModelManager("test-api-key")

        # Verify API key configuration
        mock_genai.configure.assert_called_once_with(api_key="test-api-key")

        # Verify default model names
        assert manager.primary_model_name == "gemini-2.0-flash-exp"
        assert manager.fallback_model_name == "gemini-1.5-pro"
        assert manager.timeout == 10.0  # 10000ms / 1000

        # Verify models were initialized
        assert mock_genai.GenerativeModel.call_count == 2
        mock_genai.GenerativeModel.assert_any_call("gemini-2.0-flash-exp")
        mock_genai.GenerativeModel.assert_any_call("gemini-1.5-pro")

        # Verify initial stats
        assert manager.primary_calls == 0
        assert manager.fallback_calls == 0
        assert manager.primary_failures == 0

    @patch.dict(
        os.environ,
        {
            "GEMINI_MODEL_PRIMARY": "custom-primary",
            "GEMINI_MODEL_FALLBACK": "custom-fallback",
            "GEMINI_MODEL_TIMEOUT": "5000",
        },
    )
    @patch("gemini_mcp.models.manager.genai")
    def test_init_with_env_vars(self, mock_genai):
        """Test initialization with environment variables."""
        manager = DualModelManager("test-api-key")

        assert manager.primary_model_name == "custom-primary"
        assert manager.fallback_model_name == "custom-fallback"
        assert manager.timeout == 5.0  # 5000ms / 1000

        mock_genai.GenerativeModel.assert_any_call("custom-primary")
        mock_genai.GenerativeModel.assert_any_call("custom-fallback")

    @patch("gemini_mcp.models.manager.genai")
    def test_initialize_model_success(self, mock_genai):
        """Test successful model initialization."""
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        manager = DualModelManager("test-api-key")
        assert manager._primary_model == mock_model
        assert manager._fallback_model == mock_model

    @patch("gemini_mcp.models.manager.genai")
    def test_initialize_model_failure(self, mock_genai):
        """Test model initialization failure."""
        mock_genai.GenerativeModel.side_effect = Exception("Init error")

        manager = DualModelManager("test-api-key")
        assert manager._primary_model is None
        assert manager._fallback_model is None

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_with_timeout_success(self, mock_genai):
        """Test successful generation with timeout."""
        # Setup mock model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated text"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        manager = DualModelManager("test-api-key")
        result = manager._generate_with_timeout(mock_model, "test-model", "prompt", 5.0)

        assert result == "Generated text"
        # Check that generate_content was called with prompt and request_options
        assert mock_model.generate_content.call_count == 1
        call_args = mock_model.generate_content.call_args
        assert call_args[0][0] == "prompt"
        assert "request_options" in call_args[1]
        assert call_args[1]["request_options"].timeout == 5.0

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_with_timeout_timeout_error(self, mock_genai):
        """Test generation timeout."""
        mock_model = MagicMock()

        # Mock ThreadPoolExecutor to simulate timeout
        with patch("gemini_mcp.models.manager.ThreadPoolExecutor") as mock_executor:
            mock_future = MagicMock()
            mock_future.result.side_effect = FutureTimeoutError()
            mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future

            mock_genai.GenerativeModel.return_value = mock_model
            manager = DualModelManager("test-api-key")

            with pytest.raises(TimeoutError, match="generation timed out"):
                manager._generate_with_timeout(mock_model, "test-model", "prompt", 1.0)

            mock_future.cancel.assert_called_once()

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_primary_success(self, mock_genai):
        """Test successful generation with primary model."""
        # Setup mock model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Primary response"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        manager = DualModelManager("test-api-key")
        response_text, model_used = manager.generate_content("test prompt")

        assert response_text == "Primary response"
        assert model_used == manager.primary_model_name  # Use actual model name
        assert manager.primary_calls == 1
        assert manager.fallback_calls == 0
        assert manager.primary_failures == 0

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_primary_failure_fallback_success(self, mock_genai):
        """Test primary model failure with successful fallback."""
        # Setup primary model to fail
        mock_primary = MagicMock()
        mock_primary.generate_content.side_effect = google_exceptions.GoogleAPICallError(
            "API Error"
        )

        # Setup fallback model to succeed
        mock_fallback = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Fallback response"
        mock_fallback.generate_content.return_value = mock_response

        # Configure genai to return different models
        mock_genai.GenerativeModel.side_effect = [mock_primary, mock_fallback]

        manager = DualModelManager("test-api-key")
        response_text, model_used = manager.generate_content("test prompt")

        assert response_text == "Fallback response"
        assert model_used == manager.fallback_model_name  # Use actual model name
        assert manager.primary_calls == 1
        assert manager.fallback_calls == 1
        assert manager.primary_failures == 1

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_both_models_fail(self, mock_genai):
        """Test both models failing."""
        # Setup primary model to fail with Google API error
        mock_primary = MagicMock()
        mock_primary.generate_content.side_effect = google_exceptions.GoogleAPICallError(
            "Primary API Error"
        )

        # Setup fallback model to fail with different error
        mock_fallback = MagicMock()
        mock_fallback.generate_content.side_effect = Exception("Fallback error")

        # Configure genai to return different models
        mock_genai.GenerativeModel.side_effect = [mock_primary, mock_fallback]

        manager = DualModelManager("test-api-key")

        with pytest.raises(RuntimeError, match="Both models failed"):
            manager.generate_content("test prompt")

        assert manager.primary_calls == 1
        assert manager.fallback_calls == 1
        assert manager.primary_failures == 1

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_no_models_available(self, mock_genai):
        """Test generation when no models are available."""
        # Make model initialization fail
        mock_genai.GenerativeModel.side_effect = Exception("Init error")

        manager = DualModelManager("test-api-key")

        with pytest.raises(RuntimeError, match="No models available"):
            manager.generate_content("test prompt")

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_primary_timeout_fallback_success(self, mock_genai):
        """Test primary model timeout with successful fallback."""
        # Setup primary model to timeout
        mock_primary = MagicMock()

        # Setup fallback model to succeed
        mock_fallback = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Fallback response"
        mock_fallback.generate_content.return_value = mock_response

        # Configure genai to return different models
        mock_genai.GenerativeModel.side_effect = [mock_primary, mock_fallback]

        manager = DualModelManager("test-api-key")

        # Mock the timeout for primary model
        with patch.object(manager, "_generate_with_timeout") as mock_generate_with_timeout:

            def side_effect(model, model_name, prompt, timeout):
                if model == mock_primary:
                    raise TimeoutError("Timeout")
                return "Fallback response"

            mock_generate_with_timeout.side_effect = side_effect

            response_text, model_used = manager.generate_content("test prompt")

            assert response_text == "Fallback response"
            assert model_used == manager.fallback_model_name
            assert manager.primary_failures == 1

    @patch("gemini_mcp.models.manager.genai")
    def test_generate_content_fallback_gets_more_time(self, mock_genai):
        """Test that fallback model gets 1.5x timeout."""
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        manager = DualModelManager("test-api-key")
        manager.timeout = 10.0

        with patch.object(manager, "_generate_with_timeout") as mock_generate_with_timeout:
            # Make primary fail to trigger fallback
            mock_generate_with_timeout.side_effect = [
                TimeoutError("Primary timeout"),
                "Fallback response",
            ]

            manager.generate_content("test prompt")

            # Verify fallback was called with 1.5x timeout
            assert mock_generate_with_timeout.call_count == 2
            _, _, _, primary_timeout = mock_generate_with_timeout.call_args_list[0][0]
            _, _, _, fallback_timeout = mock_generate_with_timeout.call_args_list[1][0]
            assert primary_timeout == 10.0
            assert fallback_timeout == 15.0  # 1.5x

    @patch("gemini_mcp.models.manager.genai")
    def test_get_stats(self, mock_genai):
        """Test getting usage statistics."""
        mock_genai.GenerativeModel.return_value = MagicMock()

        manager = DualModelManager("test-api-key")

        # Simulate some calls
        manager.primary_calls = 10
        manager.fallback_calls = 3
        manager.primary_failures = 2

        stats = manager.get_stats()

        assert stats["primary_model"] == manager.primary_model_name  # Use actual model name
        assert stats["fallback_model"] == manager.fallback_model_name  # Use actual model name
        assert stats["total_calls"] == 13
        assert stats["primary_calls"] == 10
        assert stats["fallback_calls"] == 3
        assert stats["primary_failures"] == 2
        assert stats["primary_success_rate"] == 0.8  # (10-2)/10
        assert stats["timeout_seconds"] == manager.timeout  # Use actual timeout

    @patch("gemini_mcp.models.manager.genai")
    def test_get_stats_no_calls(self, mock_genai):
        """Test statistics when no calls have been made."""
        mock_genai.GenerativeModel.return_value = MagicMock()

        manager = DualModelManager("test-api-key")
        stats = manager.get_stats()

        assert stats["total_calls"] == 0
        assert stats["primary_success_rate"] == 0

    @patch("gemini_mcp.models.manager.genai")
    def test_value_error_triggers_fallback(self, mock_genai):
        """Test that ValueError from primary model triggers fallback."""
        # Setup primary model to raise ValueError
        mock_primary = MagicMock()
        mock_primary.generate_content.side_effect = ValueError("Invalid input")

        # Setup fallback model to succeed
        mock_fallback = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Fallback response"
        mock_fallback.generate_content.return_value = mock_response

        # Configure genai to return different models
        mock_genai.GenerativeModel.side_effect = [mock_primary, mock_fallback]

        manager = DualModelManager("test-api-key")
        response_text, model_used = manager.generate_content("test prompt")

        assert response_text == "Fallback response"
        assert model_used == manager.fallback_model_name
        assert manager.primary_failures == 1
