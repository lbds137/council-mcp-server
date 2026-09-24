"""Tests for the TestCasesTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import council.tools.test_cases as test_cases_module
from council.tools.test_cases import TestCasesTool as CasesTool


@pytest.fixture
def manager():
    """A model manager whose generate_content returns canned test cases."""
    mgr = Mock()
    mgr.generate_content.return_value = ("1. test_empty_input", "~openai/gpt-sol-latest")
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance that exposes the manager."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


class TestCasesToolMetadata:
    """Test the static properties of TestCasesTool."""

    def test_name(self):
        """The tool registers as test_cases."""
        assert CasesTool().name == "test_cases"

    def test_description(self):
        """The description says what the tool does."""
        assert "test cases" in CasesTool().description

    def test_input_schema(self):
        """code_or_feature is required; test_type defaults to all; model is optional."""
        schema = CasesTool().input_schema
        assert schema["required"] == ["code_or_feature"]
        assert "model" in schema["properties"]
        assert schema["properties"]["test_type"]["default"] == "all"

    def test_is_cacheable(self):
        """Test-case suggestions are cacheable."""
        assert CasesTool().is_cacheable({"code_or_feature": "x"}) is True


class TestCasesToolExecute:
    """Test TestCasesTool.execute."""

    @pytest.mark.asyncio
    async def test_missing_input(self, server, manager):
        """Missing code_or_feature is rejected before any model call."""
        result = await CasesTool().execute({})
        assert result.success is False
        assert result.error == "Code or feature description is required"
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_input(self, server, manager):
        """An empty code_or_feature is treated as missing."""
        result = await CasesTool().execute({"code_or_feature": ""})
        assert result.success is False
        assert result.error == "Code or feature description is required"

    @pytest.mark.asyncio
    async def test_success_formats_response_and_footer(self, server, manager):
        """The response carries the header, the text and the model footer."""
        result = await CasesTool().execute({"code_or_feature": "def add(a, b): return a + b"})
        assert result.success is True
        assert result.result.startswith("🧪 Test Cases:")
        assert "1. test_empty_input" in result.result
        assert result.result.endswith("[Model: ~openai/gpt-sol-latest]")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "code_or_feature",
        [
            "def add(a, b):\n    return a + b",
            "Users can reset their password by email",
            "Users can classify tickets by function",  # once misread as code
        ],
    )
    async def test_prompt_embeds_input_with_one_neutral_label(
        self, server, manager, code_or_feature
    ):
        """Code and prose get the same prompt, so nothing can be mislabelled."""
        await CasesTool().execute({"code_or_feature": code_or_feature})
        prompt = manager.generate_content.call_args[0][0]
        assert code_or_feature in prompt
        assert "test cases for the following code or feature description:" in prompt
        assert "comprehensive test cases covering all aspects" in prompt

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "test_type, expected",
        [
            ("unit", "individual functions or methods in isolation"),
            ("integration", "components work together correctly"),
            ("edge", "boundary conditions"),
            ("performance", "load testing scenarios"),
        ],
    )
    async def test_prompt_uses_test_type(self, server, manager, test_type, expected):
        """Each test_type selects its own focus instruction."""
        await CasesTool().execute({"code_or_feature": "login flow", "test_type": test_type})
        prompt = manager.generate_content.call_args[0][0]
        assert expected in prompt

    @pytest.mark.asyncio
    async def test_unknown_test_type_falls_back_to_all(self, server, manager):
        """An unrecognised test_type falls back to comprehensive tests."""
        await CasesTool().execute({"code_or_feature": "login flow", "test_type": "fuzz"})
        prompt = manager.generate_content.call_args[0][0]
        assert "comprehensive test cases covering all aspects" in prompt

    @pytest.mark.asyncio
    async def test_no_model_override_passes_none(self, server, manager):
        """Without a model parameter the manager gets model=None."""
        await CasesTool().execute({"code_or_feature": "x"})
        assert manager.generate_content.call_args.kwargs["model"] is None

    @pytest.mark.asyncio
    async def test_model_override_passed_through(self, server, manager):
        """The model override reaches generate_content and the footer names the used model."""
        manager.generate_content.return_value = ("Cases", "~z-ai/glm-latest")
        result = await CasesTool().execute({"code_or_feature": "x", "model": "~z-ai/glm-latest"})
        assert manager.generate_content.call_args.kwargs["model"] == "~z-ai/glm-latest"
        assert "[Model: ~z-ai/glm-latest]" in result.result

    @pytest.mark.asyncio
    async def test_generate_content_error(self, server, manager, caplog):
        """An exception from the manager yields success=False with its message, and is logged."""
        manager.generate_content.side_effect = RuntimeError("provider down")
        with caplog.at_level(logging.ERROR):
            result = await CasesTool().execute({"code_or_feature": "x"})
        assert result.success is False
        assert result.error == "Error: provider down"
        assert "provider down" in caplog.text

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance and no bundled global, the tool reports it."""
        with patch("council._server_instance", None):
            result = await CasesTool().execute({"code_or_feature": "x"})
        assert result.success is False
        assert result.error == "Model manager not available"

    @pytest.mark.asyncio
    async def test_bundled_global_fallback(self, manager):
        """In bundled mode the module-global model_manager is used."""
        with (
            patch("council._server_instance", None),
            patch.dict(test_cases_module.__dict__, {"model_manager": manager}),
        ):
            result = await CasesTool().execute({"code_or_feature": "x"})
        assert result.success is True
        manager.generate_content.assert_called_once()
