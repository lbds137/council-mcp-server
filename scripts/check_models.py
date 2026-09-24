#!/usr/bin/env python3
"""Report registry model IDs that OpenRouter no longer lists, and stale windows.

Floating "~vendor/family-latest" aliases follow new releases on their own, but
pinned IDs and :free routes disappear without notice, and a context window
changes when an alias moves to a new model. Run this when refreshing
src/council/discovery/model_registry.py. Exits 1 if any ID is gone or any
recorded window no longer matches what most providers serve.
"""

import statistics
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


def served_window(model_id: str, listing: dict[str, dict]) -> int | None:
    """The median context window across a model's providers, or None if unknown.

    An alias has no endpoints of its own, so it is measured through its target.
    """
    target = (listing.get(model_id, {}).get("alias_target") or {}).get("slug") or model_id
    response = httpx.get(f"{OPENROUTER_MODELS_URL}/{target}/endpoints", timeout=30)
    if response.status_code != 200:
        return None
    endpoints = (response.json().get("data") or {}).get("endpoints") or []
    windows = [e["context_length"] for e in endpoints if e.get("context_length")]
    return int(statistics.median(windows)) if windows else None


def main() -> int:
    response = httpx.get(OPENROUTER_MODELS_URL, timeout=30)
    response.raise_for_status()
    listing = {model["id"]: model for model in response.json()["data"]}
    live = set(listing)

    referenced = set(MODEL_REGISTRY) | set(FREE_TIER_MODELS)
    for models in TASK_RECOMMENDATIONS.values():
        referenced.update(models)

    missing = sorted(referenced - live)
    for model_id in missing:
        print(f"gone: {model_id}")
    print(f"{len(referenced) - len(missing)}/{len(referenced)} registry IDs are live on OpenRouter")

    drifted = 0
    for model_id, metadata in MODEL_REGISTRY.items():
        if model_id in missing:
            continue
        window = served_window(model_id, listing)
        if window is not None and window != metadata.context_window:
            drifted += 1
            print(
                f"window: {model_id} records {metadata.context_window:,}, "
                f"providers now serve {window:,} (median)"
            )
    print(f"{len(MODEL_REGISTRY) - drifted}/{len(MODEL_REGISTRY)} recorded windows are current")
    return 1 if missing or drifted else 0


if __name__ == "__main__":
    sys.exit(main())
