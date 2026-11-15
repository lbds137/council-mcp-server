"""Unit tests for subscription CLI providers (Antigravity CLI and Claude Code CLI)."""

import json
import subprocess
from unittest.mock import patch

import pytest

from council.providers.base import (
    AuthenticationError,
    LLMProviderError,
    ModelNotFoundError,
    RateLimitError,
)
from council.providers.cli_sub import (
    AgyCliProvider,
    ClaudeCliProvider,
    _check_quota_gate,
    _parse_model_map,
    is_non_private_model,
    private_openrouter_extra_body,
)


class TestPrivacyFilter:
    """Tests for is_non_private_model and private_openrouter_extra_body."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "~z-ai/glm-latest",
            "z-ai/glm-5.3",
            "glm-5.3-flash",
            "~moonshotai/kimi-latest",
            "deepseek/deepseek-r1",
            "qwen/qwen3-coder:free",
            "together/qwen3-coder",
            "qwen3.8-max-0902",
            "qwq-32b",
            "google/gemma-4-31b-it:free",
            "openrouter/free",
            "openrouter/auto",
            "xiaomi/mimo-7b",
            "openai/gpt-oss-120b",
            "x-ai/grok-4",
            "grok-3",
            "minimax/minimax-m3",
            "together/deepseek-v3",
            "alibaba/qwen-max",
        ],
    )
    def test_non_private_models_detected(self, model_id):
        assert is_non_private_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "~openai/gpt-sol-latest",
            "openai/gpt-5",
            "~google/gemini-pro-latest",
            "gemini-4-argon-high",
            "mistralai/mistral-medium-3-5",
            "anthropic/claude-sonnet-4-6",
            "claude-opus",
        ],
    )
    def test_private_cleared_models_allowed(self, model_id):
        assert is_non_private_model(model_id) is False

    def test_private_openrouter_extra_body_google_and_other(self):
        google_body = private_openrouter_extra_body("~google/gemini-pro-latest")
        assert google_body["provider"]["data_collection"] == "deny"
        assert google_body["provider"]["only"] == ["google-vertex"]
        assert google_body["provider"]["allow_fallbacks"] is False

        other_body = private_openrouter_extra_body("mistralai/mistral-medium-3-5")
        assert other_body["provider"]["data_collection"] == "deny"
        assert "z-ai" in other_body["provider"]["ignore"]
        assert "deepseek" in other_body["provider"]["ignore"]
        assert "google-ai-studio" in other_body["provider"]["ignore"]


class TestModelMapAndQuotaGate:
    """Tests for _parse_model_map and _check_quota_gate helpers."""

    def test_parse_model_map_csv_and_json(self):
        assert _parse_model_map(None) == {}
        assert _parse_model_map("  ") == {}
        assert _parse_model_map("a=x, B = y ") == {"a": "x", "b": "y"}
        assert _parse_model_map('{"~google/gemini-pro-latest": "gemini-custom"}') == {
            "~google/gemini-pro-latest": "gemini-custom"
        }
        assert _parse_model_map("{bad json") == {}

    @patch("council.providers.cli_sub.subprocess.run")
    def test_quota_gate_passes_on_zero_with_devnull_and_scrubbed_env(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(["quota-ok"], 0, "ok\n", "")
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "secret-or-key"}):
            _check_quota_gate("quota-ok --check", "agy-cli", "gemini-4-argon-high")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["quota-ok", "--check"]
        assert mock_run.call_args[1]["stdin"] is subprocess.DEVNULL
        assert "OPENROUTER_API_KEY" not in mock_run.call_args[1]["env"]

    @patch("council.providers.cli_sub.subprocess.run")
    def test_quota_gate_raises_rate_limit_on_nonzero(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            ["quota-check"], 2, "weekly reserve reached\n", ""
        )
        with pytest.raises(RateLimitError) as exc_info:
            _check_quota_gate("quota-check", "claude-cli", "sonnet")
        assert "weekly reserve reached" in str(exc_info.value)

    @patch("council.providers.cli_sub.subprocess.run")
    def test_quota_gate_missing_command_raises_provider_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError("no such binary")
        with pytest.raises(LLMProviderError) as exc_info:
            _check_quota_gate("missing-gate-bin", "agy-cli", "gemini-4-argon-high")
        assert "quota command not found" in str(exc_info.value)


class TestAgyCliProvider:
    """Tests for AgyCliProvider resolution and subprocess execution."""

    def test_is_enabled_and_defaults(self):
        with patch.dict("os.environ", {"COUNCIL_AGY_CLI": "1"}, clear=True):
            assert AgyCliProvider.is_enabled() is True
            provider = AgyCliProvider()
            assert provider.pro_model == "gemini-4-argon-high"
            assert provider.flash_model == "gemini-3.8-flash-high"
        with patch.dict("os.environ", {"COUNCIL_AGY_CLI": "0"}):
            assert AgyCliProvider.is_enabled() is False

    def test_resolve_google_and_gemini_aliases(self):
        with patch.dict(
            "os.environ",
            {
                "COUNCIL_AGY_PRO_MODEL": "gemini-pro-sub",
                "COUNCIL_AGY_FLASH_MODEL": "gemini-flash-sub",
            },
        ):
            provider = AgyCliProvider()
        assert provider.resolve("~google/gemini-pro-latest") == "gemini-pro-sub"
        assert provider.resolve("google/gemini-2.5-flash") == "gemini-flash-sub"
        assert provider.resolve("gemini-pro-latest") == "gemini-pro-sub"
        assert provider.resolve("gemini-flash") == "gemini-flash-sub"
        assert provider.resolve("gemini-custom-tier") == "gemini-custom-tier"
        assert provider.resolve("google/--bad-flag") is None
        assert provider.resolve("google/gemini-2.5-pro:free") is None
        assert provider.resolve("~openai/gpt-sol-latest") is None

    def test_generate_missing_or_dash_model_and_missing_binary(self):
        provider = AgyCliProvider(binary="nonexistent-agy-bin")
        with pytest.raises(ModelNotFoundError):
            provider.generate("Hello", model=None)
        with pytest.raises(ModelNotFoundError):
            provider.generate("Hello", model="--injected-flag")
        with patch("council.providers.cli_sub.shutil.which", return_value=None):
            with pytest.raises(AuthenticationError):
                provider.generate("Hello", model="gemini-4-argon-high")

    @patch("council.providers.cli_sub.subprocess.run")
    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/agy")
    def test_generate_success_sandbox_devnull_and_leading_dash_prompt(self, _mock_which, mock_run):
        seen_settings = {}
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            settings_idx = cmd.index("--settings") + 1
            with open(cmd[settings_idx], encoding="utf-8") as fh:
                seen_settings.update(json.load(fh))
            payload = {
                "status": "SUCCESS",
                "response": "Structured Gemini answer",
                "finished_reason": "stop",
                "conversation_id": "conv-123",
            }
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        mock_run.side_effect = fake_run
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-secret"}):
            provider = AgyCliProvider(timeout=90.0, quota_cmd="")
            resp = provider.generate("--help explain consensus", model="gemini-4-argon-high")

        assert resp.content == "Structured Gemini answer"
        assert resp.model == "google/gemini-4-argon-high"
        assert "--print=--help explain consensus" in captured["cmd"]
        assert "--sandbox" in captured["cmd"]
        assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
        assert "OPENROUTER_API_KEY" not in captured["kwargs"]["env"]
        assert seen_settings["allowNonWorkspaceAccess"] is False
        assert "mcp__*" in seen_settings["permissions"]["deny"]

    @patch("council.providers.cli_sub.subprocess.run")
    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/agy")
    def test_generate_print_timeout_and_denied_actions_fail(self, _mock_which, mock_run):
        timeout_payload = {
            "status": "SUCCESS",
            "response": "partial",
            "finished_reason": "print_timeout",
        }
        mock_run.return_value = subprocess.CompletedProcess(
            ["agy"], 0, json.dumps(timeout_payload), ""
        )
        provider = AgyCliProvider(timeout=30.0, quota_cmd="")
        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("Slow prompt", model="gemini-4-argon-high")
        assert exc_info.value.is_retryable is True
        assert "print_timeout" in str(exc_info.value)

        denied_payload = {
            "status": "SUCCESS",
            "response": "Let me run a command...",
            "denied_actions": ["command(ls)"],
        }
        mock_run.return_value = subprocess.CompletedProcess(
            ["agy"], 0, json.dumps(denied_payload), ""
        )
        with pytest.raises(LLMProviderError) as denied_exc:
            provider.generate("Prompt", model="gemini-4-argon-high")
        assert "denied tool action" in str(denied_exc.value)


class TestClaudeCliProvider:
    """Tests for ClaudeCliProvider resolution and isolated subprocess flags."""

    def test_resolve_anthropic_models(self):
        provider = ClaudeCliProvider()
        assert provider.resolve("~anthropic/claude-sonnet-latest") == "sonnet"
        assert provider.resolve("anthropic/claude-opus-4-6") == "opus"
        assert provider.resolve("claude-haiku-4-5") == "haiku"
        assert provider.resolve("claude-3.7") == "claude-3.7"
        assert provider.resolve("anthropic/--bad-flag") is None
        assert provider.resolve("anthropic/claude-sonnet:beta") is None
        assert provider.resolve("google/gemini-2.5-pro") is None

    @patch("council.providers.cli_sub.subprocess.run")
    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/claude")
    def test_generate_scrubs_routing_env_isolates_settings_and_handles_dash_prompt(
        self, _mock_which, mock_run
    ):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            mcp_idx = cmd.index("--mcp-config") + 1
            with open(cmd[mcp_idx], encoding="utf-8") as fh:
                captured["mcp"] = json.load(fh)
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"is_error": False, "result": "Claude CLI reply"}), ""
            )

        mock_run.side_effect = fake_run
        with patch.dict(
            "os.environ",
            {
                "CLAUDECODE": "1",
                "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
                "ANTHROPIC_AUTH_TOKEN": "zai-tok",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
                "OPENROUTER_API_KEY": "or-secret",
                "KEEP_VAR": "yes",
            },
        ):
            provider = ClaudeCliProvider(timeout=60.0, quota_cmd="")
            resp = provider.generate("- bullet leading prompt", model="sonnet")

        assert resp.content == "Claude CLI reply"
        assert resp.model == "anthropic/claude-sonnet"
        cmd = captured["cmd"]
        assert "--strict-mcp-config" in cmd
        assert "--safe-mode" in cmd
        assert "--disable-slash-commands" in cmd
        assert "--no-session-persistence" in cmd
        ss_idx = cmd.index("--setting-sources")
        assert cmd[ss_idx + 1] == ""
        assert cmd[-2:] == ["--", "- bullet leading prompt"]
        assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
        env = captured["kwargs"]["env"]
        for forbidden in (
            "CLAUDECODE",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "OPENROUTER_API_KEY",
        ):
            assert forbidden not in env
        assert env["KEEP_VAR"] == "yes"

    @patch("council.providers.cli_sub.subprocess.run")
    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/claude")
    def test_generate_rate_limit_error_mapped(self, _mock_which, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            ["claude"],
            1,
            json.dumps({"is_error": True, "result": "Usage limit reached (429)"}),
            "",
        )
        provider = ClaudeCliProvider(quota_cmd="")
        with pytest.raises(RateLimitError):
            provider.generate("Prompt", model="sonnet")
