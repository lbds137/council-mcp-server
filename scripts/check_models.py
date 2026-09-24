#!/usr/bin/env python3
"""Report registry model IDs that OpenRouter no longer lists.

Floating "~vendor/family-latest" aliases follow new releases on their own, but
pinned IDs and :free routes disappear without notice. Run this when refreshing
src/council/discovery/model_registry.py. Exits 1 if any ID is gone.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from council.discovery.model_registry import (  # noqa: E402
    FREE_TIER_MODELS,
    MODEL_REGISTRY,
    TASK_RECOMMENDATIONS,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def main() -> int:
    response = httpx.get(OPENROUTER_MODELS_URL, timeout=30)
    response.raise_for_status()
    live = {model["id"] for model in response.json()["data"]}

    referenced = set(MODEL_REGISTRY) | set(FREE_TIER_MODELS)
    for models in TASK_RECOMMENDATIONS.values():
        referenced.update(models)

    missing = sorted(referenced - live)
    for model_id in missing:
        print(f"gone: {model_id}")
    print(f"{len(referenced) - len(missing)}/{len(referenced)} registry IDs are live on OpenRouter")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
