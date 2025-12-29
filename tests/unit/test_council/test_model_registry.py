"""Tests for the model registry module."""

from council.discovery.model_registry import (
    FREE_TIER_MODELS,
    MODEL_REGISTRY,
    TASK_RECOMMENDATIONS,
    ModelClass,
    ModelMetadata,
    TaskType,
    generate_model_guide,
    get_model_class_description,
    get_model_metadata,
    get_recommendations_for_task,
)


class TestModelClass:
    """Tests for ModelClass enum."""

    def test_flash_value(self):
        """Test FLASH enum value."""
        assert ModelClass.FLASH.value == "flash"

    def test_pro_value(self):
        """Test PRO enum value."""
        assert ModelClass.PRO.value == "pro"

    def test_deep_value(self):
        """Test DEEP enum value."""
        assert ModelClass.DEEP.value == "deep"

    def test_all_classes_exist(self):
        """Test all expected model classes exist."""
        classes = [ModelClass.FLASH, ModelClass.PRO, ModelClass.DEEP]
        assert len(classes) == 3


class TestTaskType:
    """Tests for TaskType enum."""

    def test_coding_value(self):
        """Test CODING enum value."""
        assert TaskType.CODING.value == "coding"

    def test_code_review_value(self):
        """Test CODE_REVIEW enum value."""
        assert TaskType.CODE_REVIEW.value == "code_review"

    def test_reasoning_value(self):
        """Test REASONING enum value."""
        assert TaskType.REASONING.value == "reasoning"

    def test_creative_value(self):
        """Test CREATIVE enum value."""
        assert TaskType.CREATIVE.value == "creative"

    def test_vision_value(self):
        """Test VISION enum value."""
        assert TaskType.VISION.value == "vision"

    def test_long_context_value(self):
        """Test LONG_CONTEXT enum value."""
        assert TaskType.LONG_CONTEXT.value == "long_context"

    def test_general_value(self):
        """Test GENERAL enum value."""
        assert TaskType.GENERAL.value == "general"

    def test_all_task_types_exist(self):
        """Test all expected task types exist."""
        expected_tasks = [
            TaskType.CODING,
            TaskType.CODE_REVIEW,
            TaskType.REASONING,
            TaskType.CREATIVE,
            TaskType.VISION,
            TaskType.LONG_CONTEXT,
            TaskType.GENERAL,
        ]
        assert len(expected_tasks) == 7


class TestModelMetadata:
    """Tests for ModelMetadata dataclass."""

    def test_minimal_metadata(self):
        """Test creating metadata with only required field."""
        metadata = ModelMetadata(model_class=ModelClass.PRO)
        assert metadata.model_class == ModelClass.PRO
        assert metadata.strengths == {}
        assert metadata.description == ""
        assert metadata.notes == ""
        assert metadata.recommended_for == []

    def test_full_metadata(self):
        """Test creating metadata with all fields."""
        metadata = ModelMetadata(
            model_class=ModelClass.DEEP,
            strengths={TaskType.CODING: "S", TaskType.REASONING: "A"},
            description="Test model",
            notes="Some notes",
            recommended_for=["coding", "reasoning"],
        )
        assert metadata.model_class == ModelClass.DEEP
        assert metadata.strengths[TaskType.CODING] == "S"
        assert metadata.description == "Test model"
        assert metadata.notes == "Some notes"
        assert "coding" in metadata.recommended_for


class TestModelRegistry:
    """Tests for MODEL_REGISTRY data."""

    def test_registry_not_empty(self):
        """Test registry contains models."""
        assert len(MODEL_REGISTRY) > 0

    def test_anthropic_models_present(self):
        """Test Anthropic models are in registry."""
        anthropic_models = [k for k in MODEL_REGISTRY.keys() if "anthropic" in k]
        assert len(anthropic_models) >= 3  # At least 3 Claude models

    def test_google_models_present(self):
        """Test Google models are in registry."""
        google_models = [k for k in MODEL_REGISTRY.keys() if "google" in k]
        assert len(google_models) >= 2  # At least 2 Gemini models

    def test_openai_models_present(self):
        """Test OpenAI models are in registry."""
        openai_models = [k for k in MODEL_REGISTRY.keys() if "openai" in k]
        assert len(openai_models) >= 2  # At least 2 GPT models

    def test_deepseek_models_present(self):
        """Test DeepSeek models are in registry."""
        deepseek_models = [k for k in MODEL_REGISTRY.keys() if "deepseek" in k]
        assert len(deepseek_models) >= 1

    def test_all_models_have_metadata(self):
        """Test all models have valid metadata."""
        for model_id, metadata in MODEL_REGISTRY.items():
            assert isinstance(metadata, ModelMetadata)
            assert isinstance(metadata.model_class, ModelClass)

    def test_flash_class_models_exist(self):
        """Test there are flash-class models."""
        flash_models = [k for k, v in MODEL_REGISTRY.items() if v.model_class == ModelClass.FLASH]
        assert len(flash_models) >= 2

    def test_pro_class_models_exist(self):
        """Test there are pro-class models."""
        pro_models = [k for k, v in MODEL_REGISTRY.items() if v.model_class == ModelClass.PRO]
        assert len(pro_models) >= 5

    def test_deep_class_models_exist(self):
        """Test there are deep-class models."""
        deep_models = [k for k, v in MODEL_REGISTRY.items() if v.model_class == ModelClass.DEEP]
        assert len(deep_models) >= 2


class TestTaskRecommendations:
    """Tests for TASK_RECOMMENDATIONS data."""

    def test_all_task_types_have_recommendations(self):
        """Test all task types have recommendations."""
        for task in TaskType:
            assert task in TASK_RECOMMENDATIONS
            assert len(TASK_RECOMMENDATIONS[task]) > 0

    def test_coding_has_claude_recommendation(self):
        """Test coding task recommends Claude."""
        coding_recs = TASK_RECOMMENDATIONS[TaskType.CODING]
        claude_models = [r for r in coding_recs if "claude" in r.lower()]
        assert len(claude_models) >= 1

    def test_reasoning_has_deepseek_recommendation(self):
        """Test reasoning task recommends DeepSeek R1."""
        reasoning_recs = TASK_RECOMMENDATIONS[TaskType.REASONING]
        assert any("deepseek" in r.lower() for r in reasoning_recs)

    def test_vision_has_gemini_recommendation(self):
        """Test vision task recommends Gemini."""
        vision_recs = TASK_RECOMMENDATIONS[TaskType.VISION]
        gemini_models = [r for r in vision_recs if "gemini" in r.lower()]
        assert len(gemini_models) >= 1


class TestFreeTierModels:
    """Tests for FREE_TIER_MODELS list."""

    def test_free_tier_not_empty(self):
        """Test free tier list is not empty."""
        assert len(FREE_TIER_MODELS) >= 1

    def test_free_tier_has_llama(self):
        """Test free tier includes Llama."""
        assert any("llama" in m.lower() for m in FREE_TIER_MODELS)

    def test_free_tier_models_have_free_suffix(self):
        """Test free tier models have :free suffix."""
        for model in FREE_TIER_MODELS:
            assert ":free" in model


class TestGetModelMetadata:
    """Tests for get_model_metadata function."""

    def test_exact_match(self):
        """Test getting metadata with exact model ID."""
        metadata = get_model_metadata("anthropic/claude-3.5-sonnet")
        assert metadata is not None
        assert metadata.model_class == ModelClass.PRO

    def test_with_version_suffix(self):
        """Test getting metadata with version suffix."""
        metadata = get_model_metadata("anthropic/claude-3.5-sonnet:free")
        assert metadata is not None
        assert metadata.model_class == ModelClass.PRO

    def test_fuzzy_match(self):
        """Test fuzzy matching on model name."""
        metadata = get_model_metadata("anthropic/claude-3.5-sonnet-latest")
        assert metadata is not None

    def test_unknown_model_returns_none(self):
        """Test unknown model returns None."""
        metadata = get_model_metadata("unknown/nonexistent-model")
        assert metadata is None

    def test_case_insensitive_fuzzy_match(self):
        """Test fuzzy match is case-insensitive."""
        metadata = get_model_metadata("ANTHROPIC/CLAUDE-3.5-SONNET")
        # Fuzzy match should find it
        assert metadata is not None


class TestGetRecommendationsForTask:
    """Tests for get_recommendations_for_task function."""

    def test_coding_recommendations(self):
        """Test getting recommendations for coding."""
        recs = get_recommendations_for_task(TaskType.CODING)
        assert len(recs) > 0
        assert len(recs) <= 3  # Default limit

    def test_custom_limit(self):
        """Test custom limit parameter."""
        recs = get_recommendations_for_task(TaskType.CODING, limit=1)
        assert len(recs) == 1

    def test_limit_larger_than_available(self):
        """Test limit larger than available models."""
        recs = get_recommendations_for_task(TaskType.CODING, limit=100)
        # Should return all available, not 100
        assert len(recs) <= 10

    def test_all_task_types_return_recommendations(self):
        """Test all task types return recommendations."""
        for task in TaskType:
            recs = get_recommendations_for_task(task)
            assert len(recs) > 0


class TestGetModelClassDescription:
    """Tests for get_model_class_description function."""

    def test_flash_description(self):
        """Test flash class description."""
        desc = get_model_class_description(ModelClass.FLASH)
        assert "fast" in desc.lower() or "cost" in desc.lower()

    def test_pro_description(self):
        """Test pro class description."""
        desc = get_model_class_description(ModelClass.PRO)
        assert "balanced" in desc.lower() or "most tasks" in desc.lower()

    def test_deep_description(self):
        """Test deep class description."""
        desc = get_model_class_description(ModelClass.DEEP)
        assert "quality" in desc.lower() or "complex" in desc.lower()


class TestGenerateModelGuide:
    """Tests for generate_model_guide function."""

    def test_guide_is_string(self):
        """Test guide returns a string."""
        guide = generate_model_guide()
        assert isinstance(guide, str)

    def test_guide_has_title(self):
        """Test guide has title."""
        guide = generate_model_guide()
        assert "Model Selection Guide" in guide

    def test_guide_has_task_sections(self):
        """Test guide includes task recommendations."""
        guide = generate_model_guide()
        assert "Coding" in guide
        assert "Reasoning" in guide
        assert "Vision" in guide

    def test_guide_has_class_descriptions(self):
        """Test guide includes class descriptions."""
        guide = generate_model_guide()
        assert "Flash" in guide
        assert "Pro" in guide
        assert "Deep" in guide

    def test_guide_has_free_tier_section(self):
        """Test guide includes free tier section."""
        guide = generate_model_guide()
        assert "Free Tier" in guide

    def test_guide_lists_free_models(self):
        """Test guide lists free tier models."""
        guide = generate_model_guide()
        for model in FREE_TIER_MODELS:
            assert model in guide
