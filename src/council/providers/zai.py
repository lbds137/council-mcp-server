"""Z.ai coding-plan provider for Council MCP server.

GLM calls sent here draw on the flat-rate coding plan's quota instead of
per-token billing. The API is OpenAI-compatible but takes bare model IDs
("glm-5.3", not OpenRouter's "z-ai/glm-5.3").
"""

import logging
import os
import re
import time
from typing import Any, Optional

import httpx
from openai import OpenAI

from .base import (
    AuthenticationError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    ModelInfo,
    ModelNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

ZAI_CODING_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
ZAI_MODEL_PREFIX = "z-ai/"
ZAI_MODELS_TIMEOUT_SECONDS = 10.0
ZAI_FAILED_FETCH_RETRY_SECONDS = 300.0

# OpenRouter's floating GLM aliases, resolved against Z.ai's own model list:
# the newest plain version, and the newest -flash variant
ZAI_ALIAS_PATTERNS = {
    "~z-ai/glm-latest": re.compile(r"^glm-\d+(\.\d+)?$"),
    "~z-ai/glm-flash-latest": re.compile(r"^glm-\d+(\.\d+)?-flash$"),
}

# Business codes Z.ai sends in error bodies. The 429 codes come from Z.ai's
# client tooling, as recorded by Tzurot; its docs don't list them.
ZAI_QUOTA_CODES = {"1308", "1310", "1316", "1317", "1318", "1319", "1320", "1321"}
ZAI_BUSY_CODES = {"1302", "1305", "1313"}
ZAI_ACCOUNT_CODES = {"1113", "1309"}
ZAI_MODEL_NOT_FOUND_CODE = "1214"
ZAI_CODE_PATTERN = re.compile(r"""['"]code['"]\s*:\s*['"]?(\d{4})""")


class ZaiCodingProvider(LLMProvider):
    """Provider for GLM models on the Z.ai coding plan."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 180.0,
        cache_ttl: Optional[float] = None,
    ):
        """Initialize the provider.

        Args:
            api_key: Z.ai coding-plan key. If None, reads ZAI_CODING_API_KEY.
            timeout: Request timeout in seconds. GLM reasoning can run past a
                minute, and one rate-limited attempt can take nearly two.
            cache_ttl: How long to trust Z.ai's model list, in seconds. If None,
                reads COUNCIL_CACHE_TTL (default 1 hour).
        """
        self.api_key = api_key or os.getenv("ZAI_CODING_API_KEY")
        self.timeout = timeout
        self.cache_ttl = (
            cache_ttl if cache_ttl is not None else float(os.getenv("COUNCIL_CACHE_TTL", "3600"))
        )
        self._client: Optional[OpenAI] = None
        self._models: list[dict[str, Any]] = []
        self._next_fetch: float = 0.0
        # Why the last model-list fetch failed, or None after a success
        self.list_error: Optional[str] = None

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "zai-coding"

    @property
    def client(self) -> OpenAI:
        """Get or create the OpenAI client configured for the coding plan."""
        if self._client is None:
            if not self.api_key:
                raise AuthenticationError(
                    "Z.ai coding-plan key not configured. Set ZAI_CODING_API_KEY.",
                    provider=self.name,
                )
            # One attempt only: on failure the manager falls back to OpenRouter
            self._client = OpenAI(
                base_url=ZAI_CODING_BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def _model_list(self) -> list[dict[str, Any]]:
        """Z.ai's model list, refreshed once per cache TTL.

        A failed fetch keeps the previous list (empty on first failure, which
        routes nothing to Z.ai) and retries after a few minutes.
        """
        if time.time() < self._next_fetch:
            return self._models
        try:
            response = httpx.get(
                f"{ZAI_CODING_BASE_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=ZAI_MODELS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            self._models = [m for m in response.json().get("data", []) if m.get("id")]
            self._next_fetch = time.time() + self.cache_ttl
            self.list_error = None
        except (httpx.HTTPError, ValueError) as e:
            logger.warning(f"Could not list Z.ai models: {e}")
            if isinstance(e, httpx.HTTPStatusError):
                self.list_error = f"model list returned HTTP {e.response.status_code}"
            else:
                self.list_error = f"model list unreachable ({type(e).__name__})"
            self._next_fetch = time.time() + ZAI_FAILED_FETCH_RETRY_SECONDS
        return self._models

    @staticmethod
    def is_candidate(model_id: str) -> bool:
        """Whether model_id names a GLM model the plan might carry."""
        lowered = model_id.lower()
        if ":" in lowered:
            return False
        return (
            lowered in ZAI_ALIAS_PATTERNS
            or lowered.startswith(ZAI_MODEL_PREFIX)
            or lowered.startswith("glm-")
        )

    def resolve(self, model_id: str) -> Optional[str]:
        """Return the bare Z.ai ID that serves model_id on the plan.

        Args:
            model_id: A requested model: a "~z-ai/..." alias, a "z-ai/..." ID,
                or a bare "glm-..." ID.

        Returns:
            The bare ID if the plan carries the model, or None to leave the
            request on OpenRouter (including ":free" and ":batch" routes).
        """
        if not self.is_candidate(model_id):
            return None

        lowered = model_id.lower()
        if lowered in ZAI_ALIAS_PATTERNS:
            pattern = ZAI_ALIAS_PATTERNS[lowered]
            candidates = [m for m in self._model_list() if pattern.match(m["id"])]
            if not candidates:
                return None
            newest = max(candidates, key=lambda m: (m.get("created", 0), m["id"]))
            return str(newest["id"])

        bare = lowered.removeprefix(ZAI_MODEL_PREFIX)
        for model in self._model_list():
            if model["id"].lower() == bare:
                return str(model["id"])
        return None

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response on the coding plan.

        Args:
            prompt: The prompt to send to the model.
            model: Bare Z.ai model ID, as returned by resolve().
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters for the API.

        Returns:
            LLMResponse whose model is the served model, in "z-ai/..." form.

        Raises:
            LLMProviderError: If the generation fails.
        """
        if not model:
            raise ModelNotFoundError("No Z.ai model given", provider=self.name)

        logger.info(f"Generating with Z.ai coding plan model: {model}")
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except AuthenticationError:
            raise
        except Exception as e:
            raise self._classify_error(e, model) from e

        message = response.choices[0].message
        content = message.content or ""
        if not content.strip():
            # GLM sometimes returns the whole reply in the reasoning channel
            content = getattr(message, "reasoning_content", None) or ""

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        served = response.model or model
        if not served.startswith(ZAI_MODEL_PREFIX):
            served = f"{ZAI_MODEL_PREFIX}{served}"
        return LLMResponse(
            content=content,
            model=served,
            usage=usage,
            metadata={"id": response.id, "created": response.created, "route": self.name},
        )

    def _classify_error(self, error: Exception, model: str) -> LLMProviderError:
        """Map a Z.ai API error to a provider error with a short message."""
        raw = str(error)
        logger.warning(f"Z.ai error for {model}: {raw}")
        status = getattr(error, "status_code", None)
        match = ZAI_CODE_PATTERN.search(raw)
        code = match.group(1) if match else None
        suffix = f" (Z.ai code {code})" if code else ""

        if code in ZAI_ACCOUNT_CODES or status in (401, 403):
            return AuthenticationError(f"account or key problem{suffix}", self.name, model)
        if code == ZAI_MODEL_NOT_FOUND_CODE or status == 404:
            return ModelNotFoundError(f"model not on the plan{suffix}", self.name, model)
        if code in ZAI_QUOTA_CODES:
            return RateLimitError(f"quota window exhausted{suffix}", self.name, model)
        if code in ZAI_BUSY_CODES or status == 429:
            return RateLimitError(f"busy or rate limited{suffix}", self.name, model)
        return LLMProviderError(
            raw,
            provider=self.name,
            model=model,
            is_retryable="timeout" in raw.lower(),
        )

    def list_models(self) -> list[ModelInfo]:
        """List the plan's models."""
        return [
            ModelInfo(id=f"{ZAI_MODEL_PREFIX}{m['id']}", name=m["id"], provider="z-ai")
            for m in self._model_list()
        ]

    def is_available(self) -> bool:
        """Check if the provider is configured."""
        return bool(self.api_key)
