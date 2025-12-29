"""Curated model registry with task-specific recommendations.

This module provides curated metadata about models to help users choose
the right model for their task. Data is based on benchmarks and community
feedback as of December 2025.

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


# Curated model registry - updated December 2025
# Based on benchmarks: SWE-bench, WebDev Arena, GPQA, and OpenRouter usage data
MODEL_REGISTRY: dict[str, ModelMetadata] = {
    # === Anthropic Models ===
    "anthropic/claude-3.5-sonnet": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.CODE_REVIEW: "A",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "A",
            TaskType.VISION: "A",
            TaskType.GENERAL: "A",
        },
        description="Excellent all-rounder with strong coding abilities",
        recommended_for=["code_review", "refactoring", "general"],
    ),
    "anthropic/claude-3.5-haiku": ModelMetadata(
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "B",
        },
        description="Fast and cost-effective for simpler tasks",
        recommended_for=["quick_questions", "simple_code", "summaries"],
    ),
    "anthropic/claude-sonnet-4": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "S",
            TaskType.CODE_REVIEW: "S",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "A",
            TaskType.VISION: "A",
            TaskType.GENERAL: "A",
        },
        description="State-of-the-art coding (72.5% SWE-bench)",
        notes="Leads coding benchmarks as of late 2025",
        recommended_for=["coding", "code_review", "debugging", "refactoring"],
    ),
    "anthropic/claude-opus-4": ModelMetadata(
        model_class=ModelClass.DEEP,
        strengths={
            TaskType.CODING: "S",
            TaskType.CODE_REVIEW: "S",
            TaskType.REASONING: "S",
            TaskType.CREATIVE: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "S",
        },
        description="Most capable Claude, excellent for complex tasks",
        recommended_for=["complex_reasoning", "architecture", "long_documents"],
    ),
    # === Google Models ===
    "google/gemini-2.5-pro": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "S",
            TaskType.VISION: "S",
            TaskType.LONG_CONTEXT: "S",
            TaskType.CREATIVE: "A",
            TaskType.GENERAL: "A",
        },
        description="Excellent reasoning, 1M context, leads WebDev Arena",
        notes="Best for web development and multimodal tasks",
        recommended_for=["web_development", "vision", "long_context", "reasoning"],
    ),
    "google/gemini-2.5-flash": ModelMetadata(
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.VISION: "A",
            TaskType.GENERAL: "B",
        },
        description="Fast multimodal model, good for vision tasks",
        recommended_for=["quick_vision", "image_analysis", "fast_responses"],
    ),
    "google/gemini-3-pro-preview": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "S",
            TaskType.VISION: "S",
            TaskType.LONG_CONTEXT: "S",
            TaskType.CREATIVE: "A",
            TaskType.GENERAL: "A",
        },
        description="Latest Gemini with enhanced reasoning (86.4 GPQA)",
        notes="Strong multimodal and reasoning capabilities",
        recommended_for=["reasoning", "vision", "research", "analysis"],
    ),
    # === OpenAI Models ===
    "openai/gpt-4o": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.VISION: "A",
            TaskType.CREATIVE: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong all-rounder with good speed",
        recommended_for=["general", "creative", "coding"],
    ),
    "openai/gpt-4o-mini": ModelMetadata(
        model_class=ModelClass.FLASH,
        strengths={
            TaskType.CODING: "B",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "B",
        },
        description="Cost-effective GPT-4 class model",
        recommended_for=["quick_tasks", "simple_coding", "summaries"],
    ),
    "openai/gpt-4-turbo": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.VISION: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="128K context, strong overall performance",
        recommended_for=["long_documents", "coding", "general"],
    ),
    # === DeepSeek Models ===
    "deepseek/deepseek-r1": ModelMetadata(
        model_class=ModelClass.DEEP,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "S",
            TaskType.GENERAL: "A",
        },
        description="Specialized reasoning with reinforcement learning",
        notes="Excels at math, logic, and complex coding",
        recommended_for=["complex_reasoning", "math", "logic_puzzles"],
    ),
    "deepseek/deepseek-chat": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong general-purpose model, cost-effective",
        notes="Popular open-source option",
        recommended_for=["general", "coding", "creative"],
    ),
    # === Meta Models ===
    "meta-llama/llama-3.3-70b-instruct": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong open-source model, often free tier",
        notes="Great for cost-conscious usage",
        recommended_for=["general", "coding", "free_tier"],
    ),
    "meta-llama/llama-3.1-405b-instruct": ModelMetadata(
        model_class=ModelClass.DEEP,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.LONG_CONTEXT: "A",
            TaskType.GENERAL: "A",
        },
        description="Largest Llama, 128K context",
        recommended_for=["complex_tasks", "long_context"],
    ),
    # === Mistral Models ===
    "mistralai/mistral-large": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong European model with good coding",
        recommended_for=["coding", "general", "multilingual"],
    ),
    "mistralai/mistral-medium-3": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "B",
            TaskType.GENERAL: "A",
        },
        description="90% of premium performance at $0.40/M tokens",
        notes="Best value for money",
        recommended_for=["cost_effective", "general", "coding"],
    ),
    # === xAI Models ===
    "x-ai/grok-2": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.CREATIVE: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong reasoning with real-time web integration",
        notes="Has 'Think' mode for step-by-step reasoning",
        recommended_for=["reasoning", "current_events", "creative"],
    ),
    # === Qwen Models ===
    "qwen/qwen-2.5-72b-instruct": ModelMetadata(
        model_class=ModelClass.PRO,
        strengths={
            TaskType.CODING: "A",
            TaskType.REASONING: "A",
            TaskType.GENERAL: "A",
        },
        description="Strong open-source alternative from Alibaba",
        notes="Second most used open-source on OpenRouter",
        recommended_for=["coding", "general", "multilingual"],
    ),
}


# Task-to-model recommendations based on our research
TASK_RECOMMENDATIONS: dict[TaskType, list[str]] = {
    TaskType.CODING: [
        "anthropic/claude-sonnet-4",  # SWE-bench leader
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-chat",
    ],
    TaskType.CODE_REVIEW: [
        "anthropic/claude-sonnet-4",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-3-pro-preview",
    ],
    TaskType.REASONING: [
        "deepseek/deepseek-r1",  # Specialized reasoning
        "google/gemini-3-pro-preview",  # 86.4 GPQA
        "anthropic/claude-opus-4",
        "x-ai/grok-2",
    ],
    TaskType.CREATIVE: [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "deepseek/deepseek-chat",
    ],
    TaskType.VISION: [
        "google/gemini-2.5-pro",  # Dominates vision workloads
        "google/gemini-2.5-flash",
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
    ],
    TaskType.LONG_CONTEXT: [
        "google/gemini-2.5-pro",  # 1M tokens
        "google/gemini-3-pro-preview",  # 1M tokens
        "anthropic/claude-opus-4",
        "meta-llama/llama-3.1-405b-instruct",
    ],
    TaskType.GENERAL: [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-chat",
    ],
}


# Free tier recommendations
FREE_TIER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat:free",
    "qwen/qwen-2.5-72b-instruct:free",
]


def get_model_metadata(model_id: str) -> Optional[ModelMetadata]:
    """Get curated metadata for a model.

    Args:
        model_id: The model ID (e.g., 'anthropic/claude-3.5-sonnet').

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

    # Try fuzzy match on model name
    model_lower = model_id.lower()
    for reg_id, metadata in MODEL_REGISTRY.items():
        if reg_id.lower() in model_lower or model_lower in reg_id.lower():
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
        models_str = ", ".join(r.split("/")[1] for r in recommendations)
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
