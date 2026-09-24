"""Tests for the ListModelsTool class."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import council.tools.list_models as list_models_module
from council.providers.base import LLMProviderError, ModelInfo
from council.tools.list_models import ListModelsTool

MODELS = [
    ModelInfo(
        id="~openai/gpt-sol-latest",
        name="OpenAI: GPT Sol",
        provider="openai",
        context_length=1_050_000,
        capabilities=["vision", "function_calling"],
    ),
    ModelInfo(
        id="~z-ai/glm-latest",
        name="Z.ai: GLM",
        provider="z-ai",
        context_length=200_000,
        capabilities=["code"],
    ),
    ModelInfo(
        id="meta-llama/llama-4-scout:free",
        name="Meta: Llama 4 Scout (free)",
        provider="meta-llama",
        context_length=512,
        is_free=True,
    ),
    ModelInfo(
        id="~moonshotai/kimi-latest",
        name="MoonshotAI: Kimi",
        provider="moonshotai",
        context_length=256_000,
        capabilities=["code", "function_calling"],
    ),
]


@pytest.fixture
def manager():
    """A model manager whose list_models returns a fixed catalogue."""
    mgr = Mock()
    mgr.list_models.return_value = list(MODELS)
    return mgr


@pytest.fixture
def server(manager):
    """Install a fake server instance exposing model_manager (as main.py does)."""
    instance = SimpleNamespace(model_manager=manager)
    with patch("council._server_instance", instance):
        yield instance


def _model_lines(text):
    """Return the bullet lines of a list_models result."""
    return [line for line in text.splitlines() if line.startswith("• ")]


class TestListModelsToolMetadata:
    """Test the static properties of ListModelsTool."""

    def test_name(self):
        """The tool registers as list_models."""
        assert ListModelsTool().name == "list_models"

    def test_description(self):
        """The description says what the tool does."""
        assert "List available LLM models" in ListModelsTool().description

    def test_input_schema(self):
        """All filters are optional; free_only defaults to False and limit to 20."""
        schema = ListModelsTool().input_schema
        assert schema["required"] == []
        props = schema["properties"]
        for prop in ("provider", "capability", "free_only", "search", "limit"):
            assert prop in props
        assert props["free_only"]["default"] is False
        assert props["limit"]["default"] == 20


class TestListModelsToolExecute:
    """Test ListModelsTool.execute."""

    @pytest.mark.asyncio
    async def test_lists_all_models(self, server, manager):
        """With no filters every model is listed, with a count header and legend."""
        result = await ListModelsTool().execute({})
        assert result.success is True
        assert result.result.startswith("📋 Found 4 models:")
        assert len(_model_lines(result.result)) == 4
        assert "Legend: [FLASH] Fast/cheap | [PRO] Balanced | [DEEP] Max quality" in result.result
        assert "recommend_model" in result.result

    @pytest.mark.asyncio
    async def test_line_formatting(self, server, manager):
        """Each line shows registry class, free tag, context size and capabilities."""
        result = await ListModelsTool().execute({})
        lines = _model_lines(result.result)
        assert "• ~openai/gpt-sol-latest [PRO] - 1M context (vision, function_calling)" in lines
        assert "• ~z-ai/glm-latest [PRO] - 200K context (code)" in lines
        assert "• meta-llama/llama-4-scout:free [FREE] - 512 context" in lines

    @pytest.mark.asyncio
    async def test_provider_filter(self, server, manager):
        """The provider filter keeps only that provider's models."""
        result = await ListModelsTool().execute({"provider": "z-ai"})
        lines = _model_lines(result.result)
        assert len(lines) == 1
        assert lines[0].startswith("• ~z-ai/glm-latest")

    @pytest.mark.asyncio
    async def test_capability_filter(self, server, manager):
        """The capability filter keeps only models advertising it."""
        result = await ListModelsTool().execute({"capability": "code"})
        text = result.result
        assert "Found 2 models" in text
        assert "~z-ai/glm-latest" in text
        assert "~moonshotai/kimi-latest" in text
        assert "~openai/gpt-sol-latest" not in text

    @pytest.mark.asyncio
    async def test_free_only_filter(self, server, manager):
        """free_only keeps only free-tier models."""
        result = await ListModelsTool().execute({"free_only": True})
        lines = _model_lines(result.result)
        assert len(lines) == 1
        assert "[FREE]" in lines[0]

    @pytest.mark.asyncio
    async def test_search_filter_matches_name(self, server, manager):
        """search matches against the model name as well as the ID."""
        result = await ListModelsTool().execute({"search": "kimi"})
        lines = _model_lines(result.result)
        assert len(lines) == 1
        assert "~moonshotai/kimi-latest" in lines[0]

    @pytest.mark.asyncio
    async def test_limit(self, server, manager):
        """limit caps the number of listed models."""
        result = await ListModelsTool().execute({"limit": 2})
        assert "Found 2 models" in result.result
        assert len(_model_lines(result.result)) == 2

    @pytest.mark.asyncio
    async def test_combined_filters(self, server, manager):
        """Filters combine: provider plus capability narrows to the intersection."""
        result = await ListModelsTool().execute(
            {"provider": "openai", "capability": "function_calling"}
        )
        lines = _model_lines(result.result)
        assert len(lines) == 1
        assert "~openai/gpt-sol-latest" in lines[0]

    @pytest.mark.asyncio
    async def test_no_matches(self, server, manager):
        """When nothing matches, the tool succeeds with a no-results message."""
        result = await ListModelsTool().execute({"provider": "nonexistent"})
        assert result.success is True
        assert result.result == "No models found matching the criteria."

    @pytest.mark.asyncio
    async def test_list_models_error_is_not_reported_as_empty(self, server, manager, caplog):
        """A failure to fetch the catalogue is an error, not "No models found"."""
        manager.list_models.side_effect = LLMProviderError(
            "Could not fetch the OpenRouter model list", provider="openrouter"
        )
        with caplog.at_level(logging.ERROR):
            result = await ListModelsTool().execute({})
        assert result.success is False
        assert "Could not fetch the OpenRouter model list" in result.error
        assert result.result != "No models found matching the criteria."
        assert "Could not fetch the OpenRouter model list" in caplog.text

    @pytest.mark.asyncio
    async def test_manager_without_list_models(self):
        """A manager that cannot list models is reported as unsupported."""
        with patch("council._server_instance", SimpleNamespace(model_manager=object())):
            result = await ListModelsTool().execute({})
        assert result.success is False
        assert result.error == "Manager does not support listing models"

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance and no bundled global, the tool reports it."""
        with patch("council._server_instance", None):
            result = await ListModelsTool().execute({})
        assert result.success is False
        assert result.error == "Model manager not available"

    @pytest.mark.asyncio
    async def test_bundled_global_fallback(self, manager):
        """In bundled mode the module-global model_manager is used."""
        with (
            patch("council._server_instance", None),
            patch.dict(list_models_module.__dict__, {"model_manager": manager}),
        ):
            result = await ListModelsTool().execute({})
        assert result.success is True
        manager.list_models.assert_called_once()

    @pytest.mark.asyncio
    async def test_works_without_registry(self, server, manager):
        """If the model registry cannot be imported, lines omit the class tag."""
        with patch.dict("sys.modules", {"council.discovery.model_registry": None}):
            result = await ListModelsTool().execute({"provider": "openai"})
        assert result.success is True
        lines = _model_lines(result.result)
        assert lines == ["• ~openai/gpt-sol-latest - 1M context (vision, function_calling)"]
