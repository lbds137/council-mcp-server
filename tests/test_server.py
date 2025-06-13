"""Tests for Gemini MCP Server"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import Mock, patch

import pytest

from gemini_mcp.server import DualModelManager, GeminiMCPServer


class TestDualModelManager:
    """Test the dual model manager functionality"""

    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_initialization_success(self, mock_model_class, mock_configure):
        """Test successful initialization of both models"""
        # Setup
        mock_primary = Mock()
        mock_fallback = Mock()
        mock_model_class.side_effect = [mock_primary, mock_fallback]

        # Test
        manager = DualModelManager("test_api_key")

        # Verify
        mock_configure.assert_called_once_with(api_key="test_api_key")
        assert manager.primary_model is mock_primary
        assert manager.fallback_model is mock_fallback

    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_primary_failure_uses_fallback(self, mock_model_class, mock_configure):
        """Test fallback when primary model fails"""
        # Setup
        mock_fallback = Mock()
        mock_model_class.side_effect = [Exception("Primary failed"), mock_fallback]

        # Test
        manager = DualModelManager("test_api_key")

        # Verify
        assert manager.primary_model is mock_fallback
        assert manager.fallback_model is None

    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_generate_content_primary_success(self, mock_model_class, mock_configure):
        """Test content generation with primary model"""
        # Setup
        mock_primary = Mock()
        mock_response = Mock()
        mock_response.text = "Primary response"
        mock_primary.generate_content.return_value = mock_response

        mock_model_class.side_effect = [mock_primary, Mock()]

        # Test
        manager = DualModelManager("test_api_key")
        response, model_used = manager.generate_content("Test prompt")

        # Verify
        assert response == "Primary response"
        assert "gemini-2.5-pro-preview" in model_used

    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_generate_content_fallback_on_error(self, mock_model_class, mock_configure):
        """Test fallback when primary fails during generation"""
        # Setup
        mock_primary = Mock()
        mock_primary.generate_content.side_effect = Exception("API error")

        mock_fallback = Mock()
        mock_response = Mock()
        mock_response.text = "Fallback response"
        mock_fallback.generate_content.return_value = mock_response

        mock_model_class.side_effect = [mock_primary, mock_fallback]

        # Test
        manager = DualModelManager("test_api_key")
        response, model_used = manager.generate_content("Test prompt")

        # Verify
        assert response == "Fallback response"
        assert "gemini-1.5-pro" in model_used


class TestGeminiMCPServer:
    """Test the MCP server functionality"""

    def test_server_info_no_api_key(self):
        """Test server info when no API key is set"""
        with patch.dict(os.environ, {}, clear=True):
            server = GeminiMCPServer()
            info = server._server_info()
            assert "No API Key" in info

    @patch("gemini_mcp.server.DualModelManager")
    def test_handle_initialize(self, mock_manager_class):
        """Test initialization request handling"""
        server = GeminiMCPServer()
        response = server.handle_initialize(123)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 123
        assert "protocolVersion" in response["result"]

    @patch("gemini_mcp.server.DualModelManager")
    def test_handle_tools_list(self, mock_manager_class):
        """Test tools list request"""
        server = GeminiMCPServer()
        response = server.handle_tools_list(123)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 123
        assert len(response["result"]["tools"]) == 7  # 6 Gemini tools + server_info

    @patch("gemini_mcp.server.DualModelManager")
    def test_handle_tool_call_ask_gemini(self, mock_manager_class):
        """Test ask_gemini tool call"""
        # Setup
        mock_manager = Mock()
        mock_manager.generate_content.return_value = ("Test response", "gemini-2.5-pro")
        mock_manager_class.return_value = mock_manager

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test_key"}):
            server = GeminiMCPServer()

        # Test
        params = {
            "name": "ask_gemini",
            "arguments": {"question": "What is Python?", "context": "Programming language"},
        }
        response = server.handle_tool_call(123, params)

        # Verify
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 123
        assert "Gemini's Response" in response["result"]["content"][0]["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
