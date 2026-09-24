"""Tests for the SynthesizeTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import council.tools.synthesize as synthesize_module
from council.tools.synthesize import SynthesizeTool

PERSPECTIVES = [
    {"source": "Backend team", "content": "Use Postgres for everything."},
    {"source": "Data team", "content": "Put analytics in a column store."},
]


@pytest.fixture
def manager():
    """A model manager whose generate_content returns a canned synthesis."""
    mgr = Mock()
    mgr.generate_content.return_value = ("Both agree on SQL.", "~openai/gpt-sol-latest")
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance that exposes the manager."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


class TestSynthesizeToolMetadata:
    """Test the static properties of SynthesizeTool."""

    def test_name(self):
        """The tool registers as synthesize_perspectives."""
        assert SynthesizeTool().name == "synthesize_perspectives"

    def test_description(self):
        """The description says what the tool does."""
        assert "Synthesize" in SynthesizeTool().description

    def test_input_schema(self):
        """Topic and perspectives are required; each perspective requires content."""
        schema = SynthesizeTool().input_schema
        assert schema["required"] == ["topic", "perspectives"]
        assert "model" in schema["properties"]
        perspectives = schema["properties"]["perspectives"]
        assert perspectives["type"] == "array"
        assert perspectives["items"]["required"] == ["content"]

    def test_is_cacheable(self):
        """Syntheses are cacheable."""
        assert SynthesizeTool().is_cacheable({"topic": "x"}) is True


class TestSynthesizeToolExecute:
    """Test SynthesizeTool.execute."""

    @pytest.mark.asyncio
    async def test_missing_topic(self, server, manager):
        """Missing topic is rejected before any model call."""
        result = await SynthesizeTool().execute({"perspectives": PERSPECTIVES})
        assert result.success is False
        assert result.error == "Topic is required for synthesis"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_perspectives(self, server, manager):
        """Missing perspectives are rejected."""
        result = await SynthesizeTool().execute({"topic": "Databases"})
        assert result.success is False
        assert result.error == "At least one perspective is required"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_perspectives(self, server, manager):
        """An empty perspectives list is rejected."""
        result = await SynthesizeTool().execute({"topic": "Databases", "perspectives": []})
        assert result.success is False
        assert result.error == "At least one perspective is required"

    @pytest.mark.asyncio
    async def test_success_formats_response_and_footer(self, server, manager):
        """The response carries the header, the text and the model footer."""
        result = await SynthesizeTool().execute(
            {"topic": "Databases", "perspectives": PERSPECTIVES}
        )
        assert result.success is True
        assert result.result.startswith("🔄 Synthesis:")
        assert "Both agree on SQL." in result.result
        assert result.result.endswith("[Model: ~openai/gpt-sol-latest]")

    @pytest.mark.asyncio
    async def test_prompt_contains_topic_sources_and_content(self, server, manager):
        """The prompt embeds the topic and every perspective with its source label."""
        await SynthesizeTool().execute({"topic": "Databases", "perspectives": PERSPECTIVES})
        prompt = manager.generate_content.call_args[0][0]
        assert "perspectives on: Databases" in prompt
        assert "**Backend team:**\nUse Postgres for everything." in prompt
        assert "**Data team:**\nPut analytics in a column store." in prompt

    @pytest.mark.asyncio
    async def test_perspective_without_source_is_numbered(self, server, manager):
        """A perspective without a source is labelled by its position."""
        perspectives = [
            {"source": "Ops", "content": "Keep it boring."},
            {"content": "Try something new."},
        ]
        await SynthesizeTool().execute({"topic": "Stack", "perspectives": perspectives})
        prompt = manager.generate_content.call_args[0][0]
        assert "**Perspective 2:**\nTry something new." in prompt

    @pytest.mark.asyncio
    async def test_no_model_override_passes_none(self, server, manager):
        """Without a model parameter the manager gets model=None."""
        await SynthesizeTool().execute({"topic": "x", "perspectives": PERSPECTIVES})
        assert manager.generate_content.call_args.kwargs["model"] is None

    @pytest.mark.asyncio
    async def test_model_override_passed_through(self, server, manager):
        """The model override reaches generate_content and the footer names the used model."""
        manager.generate_content.return_value = ("Synth", "~z-ai/glm-latest")
        result = await SynthesizeTool().execute(
            {"topic": "x", "perspectives": PERSPECTIVES, "model": "~z-ai/glm-latest"}
        )
        assert manager.generate_content.call_args.kwargs["model"] == "~z-ai/glm-latest"
        assert "[Model: ~z-ai/glm-latest]" in result.result

    @pytest.mark.asyncio
    async def test_generate_content_error(self, server, manager, caplog):
        """An exception from the manager yields success=False with its message, and is logged."""
        manager.generate_content.side_effect = RuntimeError("context too long")
        with caplog.at_level(logging.ERROR):
            result = await SynthesizeTool().execute({"topic": "x", "perspectives": PERSPECTIVES})
        assert result.success is False
        assert result.error == "Error: context too long"
        assert "context too long" in caplog.text

    @pytest.mark.asyncio
    async def test_perspective_without_content_is_named(self, server, manager):
        """A perspective missing its content is reported by position, without a model call."""
        result = await SynthesizeTool().execute(
            {"topic": "x", "perspectives": [{"source": "A", "content": "ok"}, {"source": "B"}]}
        )
        assert result.success is False
        assert result.error == "Perspective 2 has no content"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_source_is_numbered(self, server, manager):
        """An empty source string falls back to the position label."""
        await SynthesizeTool().execute(
            {"topic": "x", "perspectives": [{"source": "", "content": "Try it."}]}
        )
        prompt = manager.generate_content.call_args[0][0]
        assert "**Perspective 1:**\nTry it." in prompt

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance and no bundled global, the tool reports it."""
        with patch("council._server_instance", None):
            result = await SynthesizeTool().execute({"topic": "x", "perspectives": PERSPECTIVES})
        assert result.success is False
        assert result.error == "Model manager not available"

    @pytest.mark.asyncio
    async def test_bundled_global_fallback(self, manager):
        """In bundled mode the module-global model_manager is used."""
        with (
            patch("council._server_instance", None),
            patch.dict(synthesize_module.__dict__, {"model_manager": manager}),
        ):
            result = await SynthesizeTool().execute({"topic": "x", "perspectives": PERSPECTIVES})
        assert result.success is True
        manager.generate_content.assert_called_once()
