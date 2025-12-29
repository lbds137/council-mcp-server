"""Tests for the recommend_model tool."""

import pytest

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
