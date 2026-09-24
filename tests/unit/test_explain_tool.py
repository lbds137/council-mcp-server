"""Tests for the ExplainTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import council.tools.explain as explain_module
from council.tools.explain import ExplainTool


@pytest.fixture
def manager():
    """A model manager whose generate_content returns a canned explanation."""
    mgr = Mock()
    mgr.generate_content.return_value = ("A monad is a monoid...", "~openai/gpt-sol-latest")
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance that exposes the manager."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


class TestExplainToolMetadata:
    """Test the static properties of ExplainTool."""

    def test_name(self):
        """The tool registers as explain."""
        assert ExplainTool().name == "explain"

    def test_description(self):
        """The description says what the tool does."""
        assert "Explain" in ExplainTool().description

    def test_input_schema(self):
        """Topic is required; level defaults to intermediate; model is optional."""
        schema = ExplainTool().input_schema
        assert schema["required"] == ["topic"]
        assert "model" in schema["properties"]
        assert schema["properties"]["level"]["default"] == "intermediate"

    def test_is_cacheable(self):
        """Explanations are cacheable."""
        assert ExplainTool().is_cacheable({"topic": "x"}) is True


class TestExplainToolExecute:
    """Test ExplainTool.execute."""

    @pytest.mark.asyncio
    async def test_missing_topic(self, server, manager):
        """Missing topic is rejected before any model call."""
        result = await ExplainTool().execute({})
        assert result.success is False
        assert result.error == "Topic is required for explanation"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_topic(self, server, manager):
        """An empty topic is treated as missing."""
        result = await ExplainTool().execute({"topic": ""})
        assert result.success is False
        assert result.error == "Topic is required for explanation"

    @pytest.mark.asyncio
    async def test_success_formats_response_and_footer(self, server, manager):
        """The response carries the header, the text and the model footer."""
        result = await ExplainTool().execute({"topic": "monads"})
        assert result.success is True
        assert result.result.startswith("📚 Explanation:")
        assert "A monad is a monoid..." in result.result
        assert result.result.endswith("[Model: ~openai/gpt-sol-latest]")

    @pytest.mark.asyncio
    async def test_prompt_contains_topic_and_default_level(self, server, manager):
        """The prompt embeds the topic and, by default, the intermediate instructions."""
        await ExplainTool().execute({"topic": "Python's GIL"})
        prompt = manager.generate_content.call_args[0][0]
        assert "Python's GIL" in prompt
        assert "someone with programming experience" in prompt

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "level, expected",
        [
            ("beginner", "someone new to programming"),
            ("expert", "in-depth technical explanation"),
        ],
    )
    async def test_prompt_uses_requested_level(self, server, manager, level, expected):
        """The level option selects its own instruction block."""
        await ExplainTool().execute({"topic": "B-trees", "level": level})
        prompt = manager.generate_content.call_args[0][0]
        assert expected in prompt
        assert "someone with programming experience" not in prompt

    @pytest.mark.asyncio
    async def test_unknown_level_falls_back_to_intermediate(self, server, manager):
        """An unrecognised level falls back to the intermediate instructions."""
        await ExplainTool().execute({"topic": "B-trees", "level": "wizard"})
        prompt = manager.generate_content.call_args[0][0]
        assert "someone with programming experience" in prompt

    @pytest.mark.asyncio
    async def test_no_model_override_passes_none(self, server, manager):
        """Without a model parameter the manager gets model=None."""
        await ExplainTool().execute({"topic": "x"})
        assert manager.generate_content.call_args.kwargs["model"] is None

    @pytest.mark.asyncio
    async def test_model_override_passed_through(self, server, manager):
        """The model override reaches generate_content and the footer names the used model."""
        manager.generate_content.return_value = ("Explained", "~z-ai/glm-latest")
        result = await ExplainTool().execute({"topic": "x", "model": "~z-ai/glm-latest"})
        assert manager.generate_content.call_args.kwargs["model"] == "~z-ai/glm-latest"
        assert "[Model: ~z-ai/glm-latest]" in result.result

    @pytest.mark.asyncio
    async def test_generate_content_error(self, server, manager, caplog):
        """An exception from the manager yields success=False with its message, and is logged."""
        manager.generate_content.side_effect = RuntimeError("rate limited")
        with caplog.at_level(logging.ERROR):
            result = await ExplainTool().execute({"topic": "x"})
        assert result.success is False
        assert result.error == "Error: rate limited"
        assert "rate limited" in caplog.text

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance and no bundled global, the tool reports it."""
        with patch("council._server_instance", None):
            result = await ExplainTool().execute({"topic": "x"})
        assert result.success is False
        assert result.error == "Model manager not available"

    @pytest.mark.asyncio
    async def test_bundled_global_fallback(self, manager):
        """In bundled mode the module-global model_manager is used."""
        with (
            patch("council._server_instance", None),
            patch.dict(explain_module.__dict__, {"model_manager": manager}),
        ):
            result = await ExplainTool().execute({"topic": "x"})
        assert result.success is True
        manager.generate_content.assert_called_once()
