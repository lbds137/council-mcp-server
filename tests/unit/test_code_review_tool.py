"""Tests for the CodeReviewTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from council.tools.code_review import CodeReviewTool


@pytest.fixture
def manager():
    """A model manager whose generate_content returns a canned review."""
    mgr = Mock()
    mgr.generate_content.return_value = ("Looks fine overall.", "~openai/gpt-sol-latest")
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance that exposes the manager."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


class TestCodeReviewToolMetadata:
    """Test the static properties of CodeReviewTool."""

    def test_name(self):
        """The tool registers as code_review."""
        assert CodeReviewTool().name == "code_review"

    def test_description(self):
        """The description says what the tool does."""
        assert "Review code" in CodeReviewTool().description

    def test_input_schema(self):
        """Code is required; language, focus and model are optional."""
        schema = CodeReviewTool().input_schema
        assert schema["required"] == ["code"]
        for prop in ("code", "language", "focus", "model"):
            assert prop in schema["properties"]
        assert schema["properties"]["language"]["default"] == "javascript"
        assert schema["properties"]["focus"]["default"] == "general"

    def test_is_cacheable(self):
        """Reviews are cacheable because they depend only on input and model."""
        assert CodeReviewTool().is_cacheable({"code": "x = 1"}) is True


class TestCodeReviewToolExecute:
    """Test CodeReviewTool.execute."""

    @pytest.mark.asyncio
    async def test_missing_code(self, server, manager):
        """Missing code is rejected before any model call."""
        result = await CodeReviewTool().execute({})
        assert result.success is False
        assert result.error == "Code is required for review"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_code(self, server, manager):
        """An empty code string is treated as missing."""
        result = await CodeReviewTool().execute({"code": ""})
        assert result.success is False
        assert result.error == "Code is required for review"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_formats_response_and_footer(self, server, manager):
        """The response carries the review header, the text and the model footer."""
        result = await CodeReviewTool().execute({"code": "def f(): pass"})
        assert result.success is True
        assert result.result.startswith("🔍 Code Review:")
        assert "Looks fine overall." in result.result
        assert result.result.endswith("[Model: ~openai/gpt-sol-latest]")

    @pytest.mark.asyncio
    async def test_prompt_contains_code_language_and_focus(self, server, manager):
        """The prompt embeds the code, the language fence and the focus instructions."""
        await CodeReviewTool().execute(
            {"code": "query = 'SELECT ' + user_input", "language": "python", "focus": "security"}
        )
        prompt = manager.generate_content.call_args[0][0]
        assert "query = 'SELECT ' + user_input" in prompt
        assert "```python" in prompt
        assert "review the following python code" in prompt
        assert "security vulnerabilities" in prompt

    @pytest.mark.asyncio
    async def test_defaults_language_and_focus(self, server, manager):
        """Without options the prompt uses javascript and the general focus."""
        await CodeReviewTool().execute({"code": "let a = 1;"})
        prompt = manager.generate_content.call_args[0][0]
        assert "```javascript" in prompt
        assert "comprehensive review covering all aspects" in prompt

    @pytest.mark.asyncio
    async def test_no_model_override_passes_none(self, server, manager):
        """Without a model parameter the manager gets model=None (use the active model)."""
        await CodeReviewTool().execute({"code": "x = 1"})
        assert manager.generate_content.call_args.kwargs["model"] is None

    @pytest.mark.asyncio
    async def test_model_override_passed_through(self, server, manager):
        """The model override reaches generate_content and the footer names it."""
        manager.generate_content.return_value = ("Review", "~z-ai/glm-latest")
        result = await CodeReviewTool().execute({"code": "x = 1", "model": "~z-ai/glm-latest"})
        assert manager.generate_content.call_args.kwargs["model"] == "~z-ai/glm-latest"
        assert "[Model: ~z-ai/glm-latest]" in result.result

    @pytest.mark.asyncio
    async def test_footer_names_model_actually_used(self, server, manager):
        """The footer reports the model the manager used, not the one requested."""
        manager.generate_content.return_value = ("Review", "~openai/gpt-luna-latest")
        result = await CodeReviewTool().execute({"code": "x = 1", "model": "~z-ai/glm-latest"})
        assert "[Model: ~openai/gpt-luna-latest]" in result.result
        assert "[Model: ~z-ai/glm-latest]" not in result.result

    @pytest.mark.asyncio
    async def test_generate_content_error(self, server, manager, caplog):
        """An exception from the manager yields success=False with its message, and is logged."""
        manager.generate_content.side_effect = RuntimeError("upstream timeout")
        with caplog.at_level(logging.ERROR):
            result = await CodeReviewTool().execute({"code": "x = 1"})
        assert result.success is False
        assert result.error == "Error: upstream timeout"
        assert "upstream timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance, the tool reports it."""
        with patch("council._server_instance", None):
            result = await CodeReviewTool().execute({"code": "x = 1"})
        assert result.success is False
        assert result.error == "Model manager not available"

    @pytest.mark.asyncio
    async def test_server_without_manager_is_unavailable(self):
        """A server instance whose model_manager is None counts as unavailable."""
        with patch("council._server_instance", SimpleNamespace(model_manager=None)):
            result = await CodeReviewTool().execute({"code": "x = 1"})
        assert result.success is False
        assert result.error == "Model manager not available"


class TestCodeReviewToolPrompt:
    """Test CodeReviewTool._build_prompt directly."""

    @pytest.mark.parametrize(
        "focus, expected",
        [
            ("performance", "algorithmic complexity"),
            ("readability", "naming conventions"),
            ("best_practices", "Review against go best practices"),
        ],
    )
    def test_known_focus_instructions(self, focus, expected):
        """Each known focus adds its own instruction."""
        prompt = CodeReviewTool()._build_prompt("x := 1", "go", focus)
        assert expected in prompt

    def test_unknown_focus_falls_back_to_general(self):
        """An unrecognised focus falls back to the general instruction."""
        prompt = CodeReviewTool()._build_prompt("x = 1", "python", "vibes")
        assert "comprehensive review covering all aspects" in prompt
