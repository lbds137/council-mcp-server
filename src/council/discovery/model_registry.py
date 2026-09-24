"""Curated model registry with task-specific recommendations.

This module provides curated metadata about models to help users choose
the right model for their task. Data reflects benchmarks and OpenRouter
listings as of September 2026.

Anthropic models are deliberately absent: the caller is Claude Code, which
can spawn its own Claude review agents, so council is for perspectives from
other model families. They remain usable through an explicit `model` override.

The registry uses a "T-shirt sizing" system:
- flash: Fast, cost-effective, good for simple tasks
- pro: Balanced quality/cost, good for most tasks
- deep: Maximum quality, complex reasoning, long context
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModelClass(str, Enum):
    """Model class/tier for quick selection."""

    FLASH = "flash"  # Fast, cheap, good for simple tasks
    PRO = "pro"  # Balanced, good for most tasks
    DEEP = "deep"  # Maximum quality, complex reasoning


class TaskType(str, Enum):
    """Task types for model recommendations."""

    CODING = "coding"
    CODE_REVIEW = "code_review"
    REASONING = "reasoning"
    CREATIVE = "creative"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    GENERAL = "general"


@dataclass
class ModelMetadata:
    """Curated metadata for a model."""

    model_class: ModelClass
    strengths: dict[str, str] = field(default_factory=dict)  # TaskType -> S/A/B/C rating
    description: str = ""
    notes: str = ""
    recommended_for: list[str] = field(default_factory=list)


# Curated model registry, refreshed 2026-09-23.
#
# Keys are OpenRouter's floating "~vendor/family-latest" aliases where one
# exists, so a vendor's next release is picked up without editing this file.
# The comment beside each alias names the model it resolved to on 2026-09-23,
# and claims about a specific release name that release, so a claim that an
# alias has moved past reads as dated rather than wrong. Prices stay out of
# alias entries: list_models shows live pricing.
# Families without an alias (Qwen, MiniMax, Mistral) are pinned and go stale,
# as do the :free IDs; `python scripts/check_models.py` finds dead IDs.
#
# Ratings follow published benchmarks where they exist (sources are noted on
# TASK_RECOMMENDATIONS). Most of these models are too new for independent
# leaderboards, so the other ratings rest on what OpenRouter lists (context
# window, input modalities) and on the vendor's own tiering. A model's headline
# context_length on OpenRouter is the largest window any one provider serves
# (GLM-5.3 shows 1.3M because of one host; Z.ai serves 1M), so windows here
# come from the per-provider /endpoints listing.
MODEL_REGISTRY: dict[str, ModelMetadata] = {
    # === OpenAI ===
    "~openai/gpt-astra-latest": ModelMetadata(  # gpt-6-astra
        model_class=ModelClass.DEEP,
        strengths={
            TaskType.CODING: "S",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "S",
            TaskType.VISION: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="OpenAI flagship for long-horizon engineering and research",
        notes="GPT-6 Astra's 96.1% GPQA Diamond is vendor-reported",
        recommended_for=["complex_reasoning", "deep_research", "coding"],
    ),
    "~openai/gpt-sol-latest": ModelMetadata(  # gpt-6-sol
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "A",
            TaskType.VISION: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="OpenAI's cost-efficient high end",
        notes="Council's default model; GPT-6 Sol scores 57 on the Coding Agent Index",
        recommended_for=["code_review", "second_opinion", "general"],
    ),
    "~openai/gpt-luna-latest": ModelMetadata(  # gpt-6-luna
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "B",
        },
        description="OpenAI's fast, low-cost tier",
        recommended_for=["quick_tasks", "summaries", "classification"],
    ),
    # === Google ===
    "~google/gemini-pro-latest": ModelMetadata(  # gemini-3.1-pro-preview
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "S",
            TaskType.CREATIVE: "A",
            TaskType.VISION: "S",
            TaskType.LONG_CONTEXT: "S",
            TaskType.GENERAL: "A",
        },
        description="Google flagship; takes text, image, video and audio",
        notes="Gemini 3.1 Pro scores 95.5% GPQA Diamond; it dates from February 2026",
        recommended_for=["vision", "long_context", "reasoning", "research"],
    ),
    "~google/gemini-flash-latest": ModelMetadata(  # gemini-3.8-flash
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.VISION: "A",
            TaskType.GENERAL: "B",
        },
        description="Google's fast multimodal tier; takes text, image, video and audio",
        recommended_for=["quick_vision", "video", "fast_responses"],
    ),
    # === DeepSeek ===
    "~deepseek/deepseek-pro-latest": ModelMetadata(  # deepseek-v4-pro-0813
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Open-weight DeepSeek flagship with a 1M context; text-only input",
        notes="DeepSeek V4 Pro leads open models on SWE-bench Verified (80.6%)",
        recommended_for=["coding", "code_review", "cost_effective"],
    ),
    "~deepseek/deepseek-flash-latest": ModelMetadata(  # deepseek-v4.1-flash
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "B",
        },
        description="DeepSeek's sparse MoE fast tier",
        recommended_for=["quick_tasks", "cost_effective"],
    ),
    # === Moonshot ===
    "~moonshotai/kimi-latest": ModelMetadata(  # kimi-k3
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "S",
            TaskType.VISION: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Open-weight Moonshot flagship; takes text, image and video",
        notes="Kimi K3 ranks #2 on EQ-Bench creative writing",
        recommended_for=["creative", "frontend", "coding", "second_opinion"],
    ),
    # === Z.ai ===
    "~z-ai/glm-latest": ModelMetadata(  # glm-5.3
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Open-weight Z.ai flagship for software engineering; 1M context",
        notes="Text-only input",
        recommended_for=["coding", "long_context", "cost_effective"],
    ),
    "~z-ai/glm-flash-latest": ModelMetadata(  # glm-5.3-flash
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.VISION: "B",
            TaskType.GENERAL: "B",
        },
        description="Z.ai's fast tier; takes text, image and video",
        recommended_for=["quick_tasks", "quick_vision", "cost_effective"],
    ),
    # === xAI ===
    "~x-ai/grok-latest": ModelMetadata(  # grok-4.7
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.GENERAL: "A",
        },
        description="xAI flagship for coding and agentic work; 500K context",
        recommended_for=["coding", "second_opinion"],
    ),
    # === Qwen (no alias on OpenRouter, pinned) ===
    "qwen/qwen3.8-max-0902": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.VISION: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Alibaba's 2.4T MoE flagship; takes text, image and video",
        notes="$2/$6 per M tokens, 1M context",
        recommended_for=["vision", "multilingual", "general"],
    ),
    "qwen/qwen3.8-flash": ModelMetadata(
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.VISION: "A",
            TaskType.GENERAL: "B",
        },
        description="Cheap multimodal reasoning tier; long-video and document analysis",
        recommended_for=["quick_vision", "video", "cost_effective"],
    ),
    # === MiniMax (no alias on OpenRouter, pinned) ===
    "minimax/minimax-m3": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.VISION: "B",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Multimodal model for long agentic work; 1M context at $0.30/$1.20",
        recommended_for=["coding", "cost_effective"],
    ),
    # === Mistral (no alias on OpenRouter, pinned) ===
    "mistralai/mistral-medium-3-5": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "A",
        },
        description="Dense 128B European model; 262K context",
        recommended_for=["multilingual", "general"],
    ),
}


# Task-to-model recommendations, best first. The comment on each list names
# what its order rests on.
TASK_RECOMMENDATIONS: dict[TaskType, list[str]] = {
    # SWE-bench Verified, Terminal-Bench, Coding Agent Index (Sept 2026)
    TaskType.CODING: [
        "~openai/gpt-astra-latest",
        "~deepseek/deepseek-pro-latest",  # best open-weight, 80.6% SWE-bench Verified
        "~openai/gpt-sol-latest",
        "~moonshotai/kimi-latest",  # led LMArena's frontend-code board (July 2026)
        "~z-ai/glm-latest",
    ],
    # No ranked code-review benchmark exists: follows CODING, minus the
    # flagship-priced Astra, since reviews run often
    TaskType.CODE_REVIEW: [
        "~openai/gpt-sol-latest",
        "~deepseek/deepseek-pro-latest",
        "~moonshotai/kimi-latest",
        "~z-ai/glm-latest",
    ],
    # GPQA Diamond (Sept 2026)
    TaskType.REASONING: [
        "~openai/gpt-astra-latest",  # 96.1% (vendor-reported)
        "~google/gemini-pro-latest",  # 95.5%
        "~deepseek/deepseek-pro-latest",
        "~openai/gpt-sol-latest",
    ],
    # EQ-Bench Longform creative writing (Sept 2026)
    TaskType.CREATIVE: [
        "~moonshotai/kimi-latest",  # #2 overall, top non-Anthropic
        "~openai/gpt-sol-latest",  # GPT-5.6 Sol was #3; GPT-6 not yet scored
        "~google/gemini-pro-latest",
    ],
    # No vision leaderboard covers these models yet: ordered by tier, then by
    # the input modalities OpenRouter lists
    TaskType.VISION: [
        "~google/gemini-pro-latest",  # text, image, video, audio
        "qwen/qwen3.8-max-0902",  # text, image, video
        "~moonshotai/kimi-latest",  # text, image, video
        "~google/gemini-flash-latest",  # text, image, video, audio
    ],
    # No long-context benchmark covers these models yet, and all four serve
    # about 1M tokens: ordered by rating
    TaskType.LONG_CONTEXT: [
        "~google/gemini-pro-latest",  # rated S
        "~z-ai/glm-latest",
        "~deepseek/deepseek-pro-latest",
        "~openai/gpt-sol-latest",
    ],
    # LMArena text puts Gemini 3.1 Pro in its frontier tier; GPT-6 and the
    # open-weight models are not yet scored there
    TaskType.GENERAL: [
        "~google/gemini-pro-latest",
        "~openai/gpt-sol-latest",
        "~moonshotai/kimi-latest",
        "~deepseek/deepseek-pro-latest",
        "~z-ai/glm-latest",
    ],
}


# Free tier recommendations. Free routes churn fastest of all; check them with
# scripts/check_models.py.
FREE_TIER_MODELS = [
    "qwen/qwen3.8-27b:free",  # 262K, text/image/video
    "google/gemma-4-31b-it:free",  # 262K, text/image/video
    "nvidia/nemotron-3-ultra-550b-a55b:free",  # 1M, text
    "z-ai/glm-5.2:free",  # only 32K on the free route
]


def get_model_metadata(model_id: str) -> Optional[ModelMetadata]:
    """Get curated metadata for a model.

    Args:
        model_id: The model ID (e.g., '~z-ai/glm-latest').

    Returns:
        ModelMetadata if found, None otherwise.
    """
    # Try exact match first
    if model_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_id]

    # Try without version suffix (e.g., ':free', ':beta')
    base_id = model_id.split(":")[0]
    if base_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[base_id]

    # Try fuzzy match: an alias typed without its "~", or an ID that extends a
    # registry key. Not the reverse: "mistral-medium-3" is a different, older
    # model than the "mistral-medium-3-5" key it is a prefix of.
    model_lower = model_id.lower().lstrip("~")
    for reg_id, metadata in MODEL_REGISTRY.items():
        if reg_id.lower().lstrip("~") in model_lower:
            return metadata

    return None


def get_recommendations_for_task(task: TaskType, limit: int = 3) -> list[str]:
    """Get recommended models for a specific task type.

    Args:
        task: The type of task.
        limit: Maximum number of recommendations.

    Returns:
        List of recommended model IDs.
    """
    recommendations = TASK_RECOMMENDATIONS.get(task, TASK_RECOMMENDATIONS[TaskType.GENERAL])
    return recommendations[:limit]


def get_model_class_description(model_class: ModelClass) -> str:
    """Get a description of a model class.

    Args:
        model_class: The model class.

    Returns:
        Human-readable description.
    """
    descriptions = {
        ModelClass.FLASH: "Fast & cost-effective - good for simple tasks, quick responses",
        ModelClass.PRO: "Balanced quality/cost - recommended for most tasks",
        ModelClass.DEEP: "Maximum quality - complex reasoning, long context, quality-critical",
    }
    return descriptions.get(model_class, "Unknown class")


def generate_model_guide() -> str:
    """Generate a human-readable model selection guide.

    Returns:
        Markdown-formatted guide string.
    """
    lines = [
        "# Model Selection Guide",
        "",
        "## Quick Reference by Task",
        "",
    ]

    for task in TaskType:
        task_name = task.value.replace("_", " ").title()
        recommendations = get_recommendations_for_task(task, limit=3)
        models_str = ", ".join(recommendations)
        lines.append(f"**{task_name}**: {models_str}")

    lines.extend(
        [
            "",
            "## Model Classes",
            "",
            f"- **Flash**: {get_model_class_description(ModelClass.FLASH)}",
            f"- **Pro**: {get_model_class_description(ModelClass.PRO)}",
            f"- **Deep**: {get_model_class_description(ModelClass.DEEP)}",
            "",
            "## Free Tier Options",
            "",
        ]
    )

    for model in FREE_TIER_MODELS:
        lines.append(f"- {model}")

    return "\n".join(lines)
