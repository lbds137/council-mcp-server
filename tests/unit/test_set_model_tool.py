"""Tests for the SetModelTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from council.providers.base import ModelInfo
from council.tools.set_model import SetModelTool


@pytest.fixture
def manager():
    """A model manager that accepts any model and knows about GLM."""
    mgr = Mock()
    mgr.set_model.return_value = True
    mgr.active_model = "~z-ai/glm-latest"
    mgr.get_model_info.return_value = ModelInfo(
        id="~z-ai/glm-latest", name="Z.ai: GLM", provider="z-ai"
    )
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance exposing model_manager (as main.py does)."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


class TestSetModelToolMetadata:
    """Test the static properties of SetModelTool."""

    def test_name(self):
        """The tool registers as set_model."""
        assert SetModelTool().name == "set_model"

    def test_description(self):
        """The description says what the tool does."""
        assert "Change the active LLM model" in SetModelTool().description

    def test_input_schema(self):
        """The model ID is required."""
        schema = SetModelTool().input_schema
        assert schema["required"] == ["model"]
        assert schema["properties"]["model"]["type"] == "string"


class TestSetModelToolExecute:
    """Test SetModelTool.execute."""

    @pytest.mark.asyncio
    async def test_null_model_is_treated_as_missing(self, server, manager):
        """A JSON null model ID gets the required-field error, not a crash."""
        result = await SetModelTool().execute({"model": None})
        assert result.success is False
        assert result.error == "Model ID is required"
        manager.set_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_model(self, server, manager):
        """A missing model ID is rejected without touching the manager."""
        result = await SetModelTool().execute({})
        assert result.success is False
        assert result.error == "Model ID is required"
        manager.set_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_blank_model(self, server, manager):
        """A whitespace-only model ID is rejected."""
        result = await SetModelTool().execute({"model": "   "})
        assert result.success is False
        assert result.error == "Model ID is required"
        manager.set_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_switch_reports_active_model(self, server, manager):
        """A successful switch reports the manager's active_model."""
        result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is True
        assert result.result == "✓ Active model changed to: ~z-ai/glm-latest"
        manager.set_model.assert_called_once_with("~z-ai/glm-latest")

    @pytest.mark.asyncio
    async def test_reports_manager_active_model_not_input(self, server, manager):
        """The reply names what the manager says is active, not just the requested ID."""
        manager.active_model = "~openai/gpt-sol-latest"
        result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.result == "✓ Active model changed to: ~openai/gpt-sol-latest"

    @pytest.mark.asyncio
    async def test_model_id_is_stripped(self, server, manager):
        """Surrounding whitespace is stripped before the model is set."""
        await SetModelTool().execute({"model": "  ~z-ai/glm-latest\n"})
        manager.get_model_info.assert_called_once_with("~z-ai/glm-latest")
        manager.set_model.assert_called_once_with("~z-ai/glm-latest")

    @pytest.mark.asyncio
    async def test_unknown_model_still_switches(self, server, manager, caplog):
        """A model missing from the cache is still set, with a warning logged."""
        manager.get_model_info.return_value = None
        manager.active_model = "~newvendor/new-model"
        with caplog.at_level(logging.WARNING):
            result = await SetModelTool().execute({"model": "~newvendor/new-model"})
        assert result.success is True
        assert "~newvendor/new-model" in result.result
        manager.set_model.assert_called_once_with("~newvendor/new-model")
        assert "not found in cache" in caplog.text

    @pytest.mark.asyncio
    async def test_set_model_returns_false(self, server, manager):
        """If the manager refuses the model, the tool fails and names it."""
        manager.set_model.return_value = False
        result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is False
        assert result.error == "Failed to set model to ~z-ai/glm-latest"

    @pytest.mark.asyncio
    async def test_set_model_raises(self, server, manager):
        """An exception from the manager becomes success=False with its message."""
        manager.set_model.side_effect = RuntimeError("boom")
        result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is False
        assert result.error == "Error: boom"

    @pytest.mark.asyncio
    async def test_manager_without_get_model_info(self):
        """Validation is optional: a manager without get_model_info still switches."""
        mgr = SimpleNamespace(set_model=Mock(return_value=True))
        with patch("council._server_instance", SimpleNamespace(model_manager=mgr)):
            result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is True
        # Without an active_model attribute the requested ID is echoed back.
        assert result.result == "✓ Active model changed to: ~z-ai/glm-latest"

    @pytest.mark.asyncio
    async def test_manager_without_set_model(self):
        """A manager that cannot set models is reported as unsupported."""
        with patch("council._server_instance", SimpleNamespace(model_manager=object())):
            result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is False
        assert result.error == "Manager does not support setting models"

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance, the tool reports it."""
        with patch("council._server_instance", None):
            result = await SetModelTool().execute({"model": "~z-ai/glm-latest"})
        assert result.success is False
        assert result.error == "Model manager not available"
