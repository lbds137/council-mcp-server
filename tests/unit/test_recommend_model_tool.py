"""Tests for the recommend_model tool."""

import pytest

from council.discovery.model_registry import TaskType, get_recommendations_for_task
from council.tools.recommend_model import RecommendModelTool


class TestRecommendModelTool:
    """Test cases for RecommendModelTool."""

    @pytest.fixture
    def tool(self):
        """Create a RecommendModelTool instance."""
        return RecommendModelTool()

    def test_name(self, tool):
        """Test tool name property."""
        assert tool.name == "recommend_model"

    def test_description(self, tool):
        """Test tool description property."""
        desc = tool.description
        assert "recommend" in desc.lower() or "Recommend" in desc
        assert "model" in desc.lower()

    def test_input_schema_structure(self, tool):
        """Test tool input schema structure."""
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_input_schema_task_property(self, tool):
        """Test task property in schema."""
        schema = tool.input_schema
        assert "task" in schema["properties"]
        task_prop = schema["properties"]["task"]
        assert task_prop["type"] == "string"
        assert "enum" in task_prop
        # Verify all task types are in enum
        expected_tasks = [
            "coding",
            "code_review",
            "reasoning",
            "creative",
            "vision",
            "long_context",
            "general",
        ]
        for task in expected_tasks:
            assert task in task_prop["enum"]

    def test_input_schema_prefer_free(self, tool):
        """Test prefer_free property in schema."""
        schema = tool.input_schema
        assert "prefer_free" in schema["properties"]
        prop = schema["properties"]["prefer_free"]
        assert prop["type"] == "boolean"
        assert prop.get("default") is False

    def test_input_schema_prefer_fast(self, tool):
        """Test prefer_fast property in schema."""
        schema = tool.input_schema
        assert "prefer_fast" in schema["properties"]
        prop = schema["properties"]["prefer_fast"]
        assert prop["type"] == "boolean"
        assert prop.get("default") is False

    def test_input_schema_min_context(self, tool):
        """Test min_context property in schema."""
        schema = tool.input_schema
        assert "min_context" in schema["properties"]
        prop = schema["properties"]["min_context"]
        assert prop["type"] == "integer"

    def test_required_parameters(self, tool):
        """Test required parameters."""
        schema = tool.input_schema
        assert "task" in schema["required"]
        # Other parameters should be optional
        assert "prefer_free" not in schema["required"]
        assert "prefer_fast" not in schema["required"]
        assert "min_context" not in schema["required"]

    @pytest.mark.asyncio
    async def test_execute_coding_task(self, tool):
        """Test execute with coding task."""
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        assert "Coding" in result.result
        # Should include recommendations
        assert "Recommendations" in result.result
        # Should include model class guide
        assert "Flash" in result.result or "Pro" in result.result

    @pytest.mark.asyncio
    async def test_execute_shows_full_model_ids(self, tool):
        """Test recommendations print the full ID that the model parameter accepts."""
        result = await tool.execute({"task": "coding"})

        top_pick = get_recommendations_for_task(TaskType.CODING, limit=1)[0]
        assert f"**{top_pick}**" in result.result

    @pytest.mark.asyncio
    async def test_execute_reasoning_task(self, tool):
        """Test execute with reasoning task."""
        result = await tool.execute({"task": "reasoning"})
        assert result.success is True
        assert "Reasoning" in result.result
        # Should mention DeepSeek for reasoning
        assert "deepseek" in result.result.lower() or "DeepSeek" in result.result

    @pytest.mark.asyncio
    async def test_execute_vision_task(self, tool):
        """Test execute with vision task."""
        result = await tool.execute({"task": "vision"})
        assert result.success is True
        assert "Vision" in result.result
        # Should mention Gemini for vision
        assert "gemini" in result.result.lower() or "Gemini" in result.result

    @pytest.mark.asyncio
    async def test_execute_code_review_task(self, tool):
        """Test execute with code_review task."""
        result = await tool.execute({"task": "code_review"})
        assert result.success is True
        assert "Code Review" in result.result

    @pytest.mark.asyncio
    async def test_execute_creative_task(self, tool):
        """Test execute with creative task."""
        result = await tool.execute({"task": "creative"})
        assert result.success is True
        assert "Creative" in result.result

    @pytest.mark.asyncio
    async def test_execute_long_context_task(self, tool):
        """Test execute with long_context task."""
        result = await tool.execute({"task": "long_context"})
        assert result.success is True
        assert "Long Context" in result.result

    @pytest.mark.asyncio
    async def test_execute_general_task(self, tool):
        """Test execute with general task."""
        result = await tool.execute({"task": "general"})
        assert result.success is True
        assert "General" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_prefer_free(self, tool):
        """Test execute with prefer_free option."""
        result = await tool.execute({"task": "general", "prefer_free": True})
        assert result.success is True
        # Should show free tier section
        assert "Free" in result.result
        assert ":free" in result.result

    @pytest.mark.asyncio
    async def test_execute_without_prefer_free(self, tool):
        """Test execute without prefer_free option."""
        result = await tool.execute({"task": "general", "prefer_free": False})
        assert result.success is True
        # Should still succeed but may not emphasize free models
        assert "Recommendations" in result.result

    @pytest.mark.asyncio
    async def test_execute_invalid_task_fallback(self, tool):
        """Test execute with invalid task falls back to general."""
        result = await tool.execute({"task": "invalid_task"})
        assert result.success is True
        # Should fall back to general recommendations
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_execute_empty_task_fallback(self, tool):
        """Test execute with empty task falls back to general."""
        result = await tool.execute({})
        assert result.success is True
        # Should fall back to general recommendations
        assert result.result is not None

    @pytest.mark.asyncio
    async def test_execute_includes_rating_scale(self, tool):
        """Test execute includes rating scale explanation."""
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        # Should include rating scale
        assert "Rating" in result.result or "S =" in result.result

    @pytest.mark.asyncio
    async def test_execute_includes_model_classes(self, tool):
        """Test execute includes model class explanations."""
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        assert "Model Classes" in result.result

    @pytest.mark.asyncio
    async def test_execute_includes_task_specific_tip(self, tool):
        """Test execute includes task-specific tips for some tasks."""
        # Coding should have a tip
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        assert "Tip" in result.result or "SWE-bench" in result.result

    @pytest.mark.asyncio
    async def test_execute_reasoning_includes_tip(self, tool):
        """Test reasoning task includes specific tip."""
        result = await tool.execute({"task": "reasoning"})
        assert result.success is True
        assert "Tip" in result.result or "GPQA" in result.result

    @pytest.mark.asyncio
    async def test_execute_vision_includes_tip(self, tool):
        """Test vision task includes specific tip."""
        result = await tool.execute({"task": "vision"})
        assert result.success is True
        assert "Tip" in result.result

    @pytest.mark.asyncio
    async def test_execute_long_context_includes_tip(self, tool):
        """Test long_context task includes specific tip."""
        result = await tool.execute({"task": "long_context"})
        assert result.success is True
        assert "Tip" in result.result or "tokens" in result.result.lower()

    def test_get_mcp_definition(self, tool):
        """Test get_mcp_definition returns correct format."""
        definition = tool.get_mcp_definition()
        assert definition["name"] == "recommend_model"
        assert "description" in definition
        assert "inputSchema" in definition
        assert definition["inputSchema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_execute_numbered_recommendations(self, tool):
        """Test that recommendations are numbered."""
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        # Should have numbered items
        assert "1." in result.result

    @pytest.mark.asyncio
    async def test_execute_includes_model_descriptions(self, tool):
        """Test that recommendations include model descriptions."""
        result = await tool.execute({"task": "coding"})
        assert result.success is True
        # Should include some description text (italicized)
        assert "_" in result.result  # Markdown italic markers


def recommended_ids(result_text: str) -> list[str]:
    """The model IDs of the numbered recommendation lines, in order."""
    ids = []
    for line in result_text.splitlines():
        if line[:2] in {f"{n}." for n in range(1, 6)} and "**" in line:
            ids.append(line.split("**")[1])
    return ids


class TestPreferFastAndMinContext:
    """prefer_fast reorders toward flash-class models; min_context filters by window."""

    @pytest.mark.asyncio
    async def test_prefer_fast_puts_rated_flash_models_first_best_rating_first(self):
        """For vision, the A-rated flash models come before the B-rated one."""
        from council.discovery.model_registry import MODEL_REGISTRY, ModelClass

        result = await RecommendModelTool().execute({"task": "vision", "prefer_fast": True})

        ids = recommended_ids(result.result)
        flash = [m for m in ids if MODEL_REGISTRY[m].model_class == ModelClass.FLASH]
        assert ids[: len(flash)] == flash, "flash models lead the list"
        ratings = [MODEL_REGISTRY[m].strengths[TaskType.VISION] for m in flash]
        assert ratings == sorted(ratings, key="SABC".index)
        assert "~z-ai/glm-flash-latest" in flash  # rated for vision, not on the vision list
        assert "Fast (flash-class) models first" in result.result

    @pytest.mark.asyncio
    async def test_without_prefer_fast_the_curated_order_stands(self):
        """The default output is the task's curated list, unchanged."""
        result = await RecommendModelTool().execute({"task": "coding"})
        assert recommended_ids(result.result) == get_recommendations_for_task(
            TaskType.CODING, limit=5
        )

    @pytest.mark.asyncio
    async def test_min_context_drops_smaller_windows_and_names_them(self):
        """Models below the minimum are left out and listed with their windows."""
        result = await RecommendModelTool().execute({"task": "general", "min_context": 1_049_000})

        assert recommended_ids(result.result) == ["~openai/gpt-sol-latest"]
        assert "Only models serving at least 1.049M" in result.result
        assert "~moonshotai/kimi-latest (1.049M)" in result.result

    @pytest.mark.asyncio
    async def test_min_context_above_every_window_says_so(self):
        """When nothing qualifies the tool says so and points at list_models."""
        result = await RecommendModelTool().execute({"task": "coding", "min_context": 5_000_000})

        assert result.success is True
        assert recommended_ids(result.result) == []
        assert "No recommended model serves 5M tokens" in result.result

    @pytest.mark.asyncio
    async def test_each_line_shows_the_context_window(self):
        """Recommendation lines carry the model's served window."""
        result = await RecommendModelTool().execute({"task": "general"})
        assert "**~openai/gpt-sol-latest** [PRO] (Rating: A) · 1.05M context" in result.result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -5, True, "1M", 1.5])
    async def test_invalid_min_context_is_rejected(self, bad):
        """min_context must be a positive integer."""
        result = await RecommendModelTool().execute({"task": "general", "min_context": bad})
        assert result.success is False
        assert result.error == "min_context must be a positive number of tokens"

    def test_token_labels_keep_near_values_apart(self):
        """1,048,576 and 1,050,000 get different labels."""
        from council.tools.recommend_model import _tokens

        assert _tokens(1_048_576) == "1.049M"
        assert _tokens(1_050_000) == "1.05M"
        assert _tokens(1_000_000) == "1M"
        assert _tokens(262_144) == "262K"

    @pytest.mark.asyncio
    async def test_only_models_that_would_have_been_listed_are_named(self, monkeypatch):
        """A small-window model below the top five isn't reported as left out."""
        from council.discovery import model_registry

        coding = list(model_registry.TASK_RECOMMENDATIONS[TaskType.CODING])
        monkeypatch.setitem(
            model_registry.TASK_RECOMMENDATIONS,
            TaskType.CODING,
            [*coding, "mistralai/mistral-medium-3-5"],  # 262K, sixth in line
        )

        result = await RecommendModelTool().execute({"task": "coding", "min_context": 500_000})

        assert len(recommended_ids(result.result)) == 5
        assert "Left out" not in result.result
