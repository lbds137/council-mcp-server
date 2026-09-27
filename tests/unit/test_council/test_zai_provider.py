"""Tests for the Z.ai coding-plan provider."""

from unittest.mock import Mock, patch

import httpx
import pytest

from council.providers.base import (
    AuthenticationError,
    LLMProviderError,
    ModelNotFoundError,
    RateLimitError,
)
from council.providers.zai import ZAI_CODING_BASE_URL, ZaiCodingProvider

# Z.ai's /models response as probed on 2026-09-23 (trimmed)
PLAN_MODELS = {
    "data": [
        {"id": "glm-4.7", "created": 1766332800},
        {"id": "glm-5.1", "created": 1774620000},
        {"id": "glm-5.2", "created": 1781625600},
        {"id": "glm-5.3", "created": 1786636800},
        {"id": "glm-5.3-flash", "created": 1786636800},
        {"id": "glm-5.3-flashx", "created": 1786636800},
        {"id": "glm-5-turbo", "created": 1773504000},
    ]
}


def models_response(payload=PLAN_MODELS) -> Mock:
    """An httpx response carrying a model list."""
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class FakeAPIError(Exception):
    """Stands in for the OpenAI SDK's APIStatusError."""

    def __init__(self, message: str, status_code=None, code=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class FakeStream:
    """Stands in for the OpenAI SDK's Stream[ChatCompletionChunk].

    Supports iteration and the context-manager protocol, the things generate()
    uses. Iteration can optionally raise partway through, to stand in for a
    connection drop mid-stream.
    """

    def __init__(self, chunks, raise_after: Exception | None = None):
        self._chunks = list(chunks)
        self._raise_after = raise_after
        self.closed = False

    def __iter__(self):
        yield from self._chunks
        if self._raise_after is not None:
            raise self._raise_after

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.closed = True
        return False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def provider():
    """A provider with a key and a fixed cache TTL."""
    return ZaiCodingProvider(api_key="zai-test-key", cache_ttl=3600)


class TestResolve:
    """Tests for mapping requested model IDs to the plan's bare IDs."""

    @patch("council.providers.zai.httpx.get")
    def test_latest_alias_resolves_to_newest_plain_version(self, mock_get, provider):
        """Test ~z-ai/glm-latest picks the newest glm-X.Y, not a variant."""
        mock_get.return_value = models_response()
        assert provider.resolve("~z-ai/glm-latest") == "glm-5.3"

    @patch("council.providers.zai.httpx.get")
    def test_flash_alias_resolves_to_newest_flash(self, mock_get, provider):
        """Test ~z-ai/glm-flash-latest picks -flash and not -flashx."""
        mock_get.return_value = models_response()
        assert provider.resolve("~z-ai/glm-flash-latest") == "glm-5.3-flash"

    @patch("council.providers.zai.httpx.get")
    def test_prefixed_and_bare_ids_resolve_when_on_the_plan(self, mock_get, provider):
        """Test OpenRouter-style and bare IDs both map to the plan's ID."""
        mock_get.return_value = models_response()
        assert provider.resolve("z-ai/glm-5.1") == "glm-5.1"
        assert provider.resolve("GLM-5.2") == "glm-5.2"

    @patch("council.providers.zai.httpx.get")
    def test_models_off_the_plan_stay_on_openrouter(self, mock_get, provider):
        """Test GLM IDs the plan doesn't list, and :free routes, resolve to None."""
        mock_get.return_value = models_response()
        assert provider.resolve("z-ai/glm-5.3-prime") is None
        assert provider.resolve("z-ai/glm-5.2:free") is None

    @patch("council.providers.zai.httpx.get")
    def test_non_glm_models_skip_the_model_fetch(self, mock_get, provider):
        """Test other families never trigger a call to Z.ai."""
        assert provider.resolve("~openai/gpt-sol-latest") is None
        mock_get.assert_not_called()

    @patch("council.providers.zai.httpx.get")
    def test_model_list_is_cached(self, mock_get, provider):
        """Test the model list is fetched once per TTL."""
        mock_get.return_value = models_response()
        provider.resolve("z-ai/glm-5.3")
        provider.resolve("~z-ai/glm-latest")
        assert mock_get.call_count == 1
        assert mock_get.call_args[0][0] == f"{ZAI_CODING_BASE_URL}/models"

    @patch("council.providers.zai.httpx.get")
    def test_failed_fetch_routes_nothing_and_backs_off(self, mock_get, provider):
        """Test an unreachable Z.ai leaves GLM on OpenRouter without refetching every call."""
        mock_get.side_effect = httpx.ConnectError("down")
        assert provider.resolve("~z-ai/glm-latest") is None
        assert provider.resolve("z-ai/glm-5.3") is None
        assert mock_get.call_count == 1
        assert provider.list_error == "model list unreachable (ConnectError)"

    @patch("council.providers.zai.httpx.get")
    def test_rejected_key_is_reported_then_cleared(self, mock_get, provider):
        """Test a 401 from the model list is recorded, and a later success clears it."""
        request = httpx.Request("GET", f"{ZAI_CODING_BASE_URL}/models")
        rejected = Mock()
        rejected.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=request, response=httpx.Response(401, request=request)
        )
        mock_get.return_value = rejected
        provider.resolve("z-ai/glm-5.3")
        assert provider.list_error == "model list returned HTTP 401"

        provider._next_fetch = 0.0
        mock_get.return_value = models_response()
        assert provider.resolve("z-ai/glm-5.3") == "glm-5.3"
        assert provider.list_error is None

    @pytest.mark.parametrize(
        "payload",
        [[{"id": "glm-5.3"}], {"data": None}, {"data": []}, {"error": {"code": "1309"}}],
    )
    @patch("council.providers.zai.httpx.get")
    def test_unusable_model_list_is_reported_not_cached(self, mock_get, provider, payload):
        """Test an odd or empty 200 body routes nothing and says the list is unreadable."""
        mock_get.return_value = models_response(payload)

        assert provider.resolve("~z-ai/glm-latest") is None
        assert provider.list_error == "model list unreadable (no models listed)"

    @patch("council.providers.zai.httpx.get")
    def test_entries_with_missing_fields_are_tolerated(self, mock_get, provider):
        """Test entries without an id or date don't break resolution."""
        mock_get.return_value = models_response(
            {"data": [{"id": "glm-5.2", "created": None}, {"object": "model"}, {"id": "glm-5.3"}]}
        )

        assert provider.resolve("~z-ai/glm-latest") in ("glm-5.2", "glm-5.3")
        assert provider.list_error is None

    def test_is_candidate(self):
        """Test which IDs could be on the plan."""
        assert ZaiCodingProvider.is_candidate("~z-ai/glm-latest")
        assert ZaiCodingProvider.is_candidate("z-ai/glm-5.3")
        assert ZaiCodingProvider.is_candidate("glm-5.3")
        assert not ZaiCodingProvider.is_candidate("z-ai/glm-5.2:free")
        assert not ZaiCodingProvider.is_candidate("~openai/gpt-sol-latest")


class TestGenerate:
    """Tests for generation on the plan."""

    def _chunk(
        self,
        content=None,
        reasoning=None,
        finish_reason=None,
        usage=None,
        id="req-1",
        created=1790000000,
        model="glm-5.3",
    ) -> Mock:
        """A single streamed ChatCompletionChunk, as the OpenAI SDK returns it."""
        delta = Mock(content=content, reasoning_content=reasoning)
        choice = Mock(delta=delta, finish_reason=finish_reason)
        chunk = Mock(id=id, created=created, model=model, usage=usage)
        chunk.choices = [choice]
        return chunk

    def completion(
        self, content="Plan response", reasoning=None, model="glm-5.3", finish_reason="stop"
    ) -> FakeStream:
        """A two-chunk stream: the content/reasoning, then a final chunk with
        usage and finish_reason (Z.ai puts usage on a final chunk that still
        carries a non-empty choices list)."""
        usage = Mock(prompt_tokens=5, completion_tokens=7, total_tokens=12)
        chunks = [
            self._chunk(content=content, reasoning=reasoning, model=model),
            self._chunk(content="", finish_reason=finish_reason, usage=usage, model=model),
        ]
        return FakeStream(chunks)

    @patch("council.providers.zai.OpenAI")
    def test_generate_uses_plan_endpoint_and_bare_id(self, mock_openai, provider):
        """Test the request goes to the coding endpoint, once, with the bare ID."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion()

        response = provider.generate("Hello", model="glm-5.3")

        client_kwargs = mock_openai.call_args[1]
        assert client_kwargs["base_url"] == ZAI_CODING_BASE_URL
        assert client_kwargs["max_retries"] == 0
        create_kwargs = mock_openai.return_value.chat.completions.create.call_args[1]
        assert create_kwargs["model"] == "glm-5.3"
        assert response.content == "Plan response"
        assert response.model == "z-ai/glm-5.3"
        assert response.metadata["route"] == "zai-coding"

    @patch("council.providers.zai.OpenAI")
    def test_stream_requested_with_usage_included(self, mock_openai, provider):
        """Test the request streams and asks Z.ai to include usage on the final chunk."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion()

        provider.generate("Hello", model="glm-5.3")

        create_kwargs = mock_openai.return_value.chat.completions.create.call_args[1]
        assert create_kwargs["stream"] is True
        assert create_kwargs["stream_options"] == {"include_usage": True}

    @patch("council.providers.zai.OpenAI")
    def test_content_assembled_across_chunks(self, mock_openai, provider):
        """Test streamed content deltas are concatenated in order."""
        usage = Mock(prompt_tokens=5, completion_tokens=7, total_tokens=12)
        chunks = [
            self._chunk(content="Pl"),
            self._chunk(content="an "),
            self._chunk(content="response", finish_reason="stop", usage=usage),
        ]
        mock_openai.return_value.chat.completions.create.return_value = FakeStream(chunks)

        response = provider.generate("Hello", model="glm-5.3")

        assert response.content == "Plan response"

    @patch("council.providers.zai.OpenAI")
    def test_usage_taken_from_final_chunk_with_choices(self, mock_openai, provider):
        """Test usage is read from the final chunk, which still has a non-empty choices list."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion()

        response = provider.generate("Hello", model="glm-5.3")

        assert response.usage == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}

    @patch("council.providers.zai.OpenAI")
    def test_reply_in_reasoning_channel_is_used(self, mock_openai, provider):
        """Test an empty content with the reply in reasoning_content still returns it."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion(
            content="", reasoning="The answer"
        )

        assert provider.generate("Hello", model="glm-5.3").content == "The answer"

    @patch("council.providers.zai.OpenAI")
    def test_reasoning_cut_off_by_token_limit_is_an_error(self, mock_openai, provider):
        """Test partial reasoning isn't passed off as the answer."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion(
            content="", reasoning="Let me think about", finish_reason="length"
        )

        with pytest.raises(LLMProviderError, match="cut off"):
            provider.generate("Hello", model="glm-5.3")

    @patch("council.providers.zai.OpenAI")
    def test_malformed_reply_becomes_a_provider_error(self, mock_openai, provider):
        """Test a stream with no choices at all raises a provider error, so the
        manager falls back."""
        chunk = Mock(id="req-1", created=1790000000, model="glm-5.3", usage=None)
        chunk.choices = []
        mock_openai.return_value.chat.completions.create.return_value = FakeStream([chunk])

        with pytest.raises(LLMProviderError):
            provider.generate("Hello", model="glm-5.3")

    @patch("council.providers.zai.OpenAI")
    def test_exception_during_iteration_is_classified(self, mock_openai, provider):
        """Test a connection drop mid-stream is classified like a create()-time error."""
        stream = FakeStream(
            [self._chunk(content="Pl")], raise_after=FakeAPIError("Connection error.")
        )
        mock_openai.return_value.chat.completions.create.return_value = stream

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Hello", model="glm-5.3")

        assert exc_info.value.provider == "zai-coding"
        assert str(exc_info.value) == "Connection error."
        assert stream.closed is True

    @patch("council.providers.zai.OpenAI")
    def test_mid_stream_error_code_is_read_from_the_code_attribute(self, mock_openai, provider):
        """Test a mid-stream SSE error, which has no status_code, is classified from .code."""
        stream = FakeStream(
            [self._chunk(content="Pl")],
            raise_after=FakeAPIError("Connection error.", code="1308"),
        )
        mock_openai.return_value.chat.completions.create.return_value = stream

        with pytest.raises(RateLimitError) as exc_info:
            provider.generate("Hello", model="glm-5.3")

        assert str(exc_info.value) == "quota window exhausted (Z.ai code 1308)"

    @patch("council.providers.zai.OpenAI")
    def test_stream_and_stream_options_kwargs_cannot_be_overridden(self, mock_openai, provider):
        """Test caller-supplied stream kwargs never collide with this provider's own."""
        mock_openai.return_value.chat.completions.create.return_value = self.completion()

        provider.generate("Hello", model="glm-5.3", stream=False, stream_options={"x": 1})

        create_kwargs = mock_openai.return_value.chat.completions.create.call_args[1]
        assert create_kwargs["stream"] is True
        assert create_kwargs["stream_options"] == {"include_usage": True}

    @patch("council.providers.zai.OpenAI")
    @patch("council.providers.zai.time.monotonic")
    def test_deadline_exceeded_closes_stream_and_raises(
        self, mock_monotonic, mock_openai, provider
    ):
        """Test an overall deadline is enforced, since the SDK timeout is per-read only."""
        stream = FakeStream(
            [self._chunk(content="Pl"), self._chunk(content="an", finish_reason="stop")]
        )
        mock_openai.return_value.chat.completions.create.return_value = stream
        mock_monotonic.side_effect = [0.0, provider.timeout + 1]

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Hello", model="glm-5.3")

        assert exc_info.value.is_retryable is True
        assert "no complete reply" in str(exc_info.value)
        assert stream.closed is True

    @patch("council.providers.zai.OpenAI")
    def test_served_model_falls_back_to_requested_when_chunks_carry_none(
        self, mock_openai, provider
    ):
        """Test the served model in metadata falls back to the requested model."""
        usage = Mock(prompt_tokens=5, completion_tokens=7, total_tokens=12)
        chunk = self._chunk(content="Plan response", model=None, finish_reason="stop", usage=usage)
        mock_openai.return_value.chat.completions.create.return_value = FakeStream([chunk])

        response = provider.generate("Hello", model="glm-5.3")

        assert response.model == "z-ai/glm-5.3"

    @pytest.mark.parametrize(
        "error,expected_class,expected_message",
        [
            (
                FakeAPIError("Error code: 429 - {'error': {'code': '1308'}}", 429),
                RateLimitError,
                "quota window exhausted (Z.ai code 1308)",
            ),
            (
                FakeAPIError("Error code: 429 - {'error': {'code': '1305'}}", 429),
                RateLimitError,
                "busy or rate limited (Z.ai code 1305)",
            ),
            (
                FakeAPIError('Error code: 400 - {"code":"1214","message":"modelCode"}', 400),
                ModelNotFoundError,
                "model not on the plan (Z.ai code 1214)",
            ),
            (
                FakeAPIError(
                    "Error code: 400 - {'error': {'code': '1211', "
                    "'message': 'Unknown Model, please check the model code.'}}",
                    400,
                ),
                ModelNotFoundError,
                "model not on the plan (Z.ai code 1211)",
            ),
            (FakeAPIError("Error code: 401 - unauthorized", 401), AuthenticationError, None),
            (FakeAPIError("connection reset", None), LLMProviderError, "connection reset"),
            (
                FakeAPIError("Error code: 429 - {'error': {'code': '13081'}}", 429),
                RateLimitError,
                "busy or rate limited",
            ),
        ],
    )
    @patch("council.providers.zai.OpenAI")
    def test_errors_are_classified(
        self, mock_openai, provider, error, expected_class, expected_message
    ):
        """Test Z.ai errors map to provider errors with short messages."""
        mock_openai.return_value.chat.completions.create.side_effect = error

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Hello", model="glm-5.3")

        assert type(exc_info.value) is expected_class
        assert exc_info.value.provider == "zai-coding"
        if expected_message:
            assert str(exc_info.value) == expected_message

    @patch("council.providers.zai.OpenAI")
    def test_sdk_timeout_is_retryable(self, mock_openai, provider):
        """Test the SDK's "Request timed out." message counts as a timeout."""
        mock_openai.return_value.chat.completions.create.side_effect = FakeAPIError(
            "Request timed out."
        )

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Hello", model="glm-5.3")

        assert exc_info.value.is_retryable is True

    def test_generate_without_key_is_an_auth_error(self, monkeypatch):
        """Test a provider without a key fails clearly."""
        monkeypatch.delenv("ZAI_CODING_API_KEY", raising=False)
        with pytest.raises(AuthenticationError):
            ZaiCodingProvider().generate("Hello", model="glm-5.3")
