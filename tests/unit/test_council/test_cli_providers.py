"""Unit tests for subscription CLI providers and private_only vendor/host gates."""

import json
import signal
import subprocess
from unittest.mock import MagicMock, patch

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
    CLITimeoutError,
    _check_quota_gate,
    _parse_model_map,
    _scrubbed_child_env,
    is_excluded_model,
    is_non_private_model,
    private_openrouter_extra_body,
    private_openrouter_providers,
)


def _mock_popen_factory(returncode=0, stdout="", stderr="", side_effect=None, capture=None):
    """Build a Popen mock compatible with _run_isolated_subprocess."""

    def _factory(cmd, **kwargs):
        if capture is not None:
            capture["cmd"] = cmd
            capture["kwargs"] = kwargs
            if "--settings" in cmd:
                idx = cmd.index("--settings") + 1
                with open(cmd[idx], encoding="utf-8") as fh:
                    capture["settings"] = json.load(fh)
            if "--mcp-config" in cmd:
                idx = cmd.index("--mcp-config") + 1
                with open(cmd[idx], encoding="utf-8") as fh:
                    capture["mcp"] = json.load(fh)
        if side_effect is not None and not isinstance(side_effect, subprocess.TimeoutExpired):
            raise side_effect
        proc = MagicMock()
        proc.pid = 42424
        proc.returncode = returncode
        if isinstance(side_effect, subprocess.TimeoutExpired):
            calls = {"n": 0}

            def _comm(input=None, timeout=None):
                if capture is not None and input is not None:
                    capture["stdin_text"] = input
                calls["n"] += 1
                if calls["n"] == 1:
                    raise side_effect
                return ("", "")

            proc.communicate.side_effect = _comm
        else:

            def _comm_ok(input=None, timeout=None):
                if capture is not None:
                    capture["stdin_text"] = input
                    capture["timeout"] = timeout
                return (stdout, stderr)

            proc.communicate.side_effect = _comm_ok
        return proc

    return _factory


class TestPrivacyAllowlistAndPolicyGate:
    """Tests for strict 5-vendor private_only allowlist and global xAI exclusion."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "~moonshotai/kimi-latest",
            "deepseek/deepseek-r1",
            "qwen/qwen3-coder",
            "qwen/qwen3-coder:free",
            "together/qwen3-coder",
            "qwen3.8-max-0902",
            "qwq-32b",
            "google/gemma-4-31b-it",
            "google/gemma-4-31b-it:free",
            "google/gemini-2.5-pro:free",
            "openai/gpt-5@preset/custom-roulette",
            "openai/gpt-5@preset",
            "@preset/pin-glm-fast",
            "~~openai/gpt-5",
            "openai/ gpt-oss-120b",
            "openrouter/x-ai/grok-4",
            "~ x-ai/aurora",
            "grok4",
            "openrouter/free",
            "openrouter/auto",
            "xiaomi/mimo-7b",
            "openai/gpt-oss-120b",
            "bytedance-seed/seed-oss-36b",
            "stepfun-ai/step-3",
            "kwaipilot/kat-dev",
            "meituan/longcat-flash",
            "x-ai/grok-4",
            "xai/grok-3",
            "grok-3",
            "minimax/minimax-m3",
            "together/deepseek-v3",
            "alibaba/qwen-max",
        ],
    )
    def test_non_private_models_rejected(self, model_id):
        assert private_openrouter_providers(model_id) is None
        assert is_non_private_model(model_id) is True

    @pytest.mark.parametrize(
        ("model_id", "expected_only"),
        [
            ("~openai/gpt-sol-latest", ["openai"]),
            ("openai/gpt-5", ["openai"]),
            ("~google/gemini-pro-latest", ["google-vertex"]),
            ("gemini-4-argon-high", ["google-vertex"]),
            ("mistralai/mistral-medium-3-5", ["mistral"]),
            ("anthropic/claude-sonnet-4-6", ["anthropic"]),
            ("claude-opus", ["anthropic"]),
            ("~z-ai/glm-latest", ["mistral"]),
            ("z-ai/glm-5.3", ["mistral"]),
            ("glm-5.3-flash", ["mistral"]),
        ],
    )
    def test_private_allowlist_pins_exact_provider(self, model_id, expected_only):
        assert private_openrouter_providers(model_id) == expected_only
        assert is_non_private_model(model_id) is False
        body = private_openrouter_extra_body(
            model_id, existing={"provider": {"ignore": ["foo"]}, "transforms": []}
        )
        assert body["transforms"] == []
        assert body["provider"] == {
            "data_collection": "deny",
            "only": expected_only,
            "allow_fallbacks": False,
        }

    def test_private_openrouter_extra_body_raises_on_unlisted_vendor(self):
        with pytest.raises(LLMProviderError) as exc_info:
            private_openrouter_extra_body("moonshotai/kimi-k2.5")
        assert exc_info.value.provider == "privacy-gate"
        assert exc_info.value.is_retryable is False

    @pytest.mark.parametrize(
        ("model_id", "excluded"),
        [
            ("x-ai/grok-4", True),
            ("~xai/grok-latest", True),
            ("openrouter/x-ai/grok-4", True),
            ("~ x-ai/aurora", True),
            ("grok-3:beta", True),
            ("grok4", True),
            ("grok", True),
            ("openai/gpt-5", False),
            ("z-ai/glm-5.3", False),
        ],
    )
    def test_global_xai_exclusion(self, model_id, excluded):
        assert is_excluded_model(model_id) is excluded


class TestEnvAllowlistAndQuotaGate:
    """Tests for _scrubbed_child_env, _parse_model_map, and _check_quota_gate."""

    def test_scrubbed_child_env_uses_strict_allowlist(self):
        fake_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/testuser",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "OPENROUTER_API_KEY": "sk-or-secret",
            "ZAI_CODING_API_KEY": "zai-secret",
            "GEMINI_API_KEY": "gem-secret",
            "GOOGLE_API_KEY": "goog-secret",
            "ANTHROPIC_API_KEY": "ant-secret",
            "GITHUB_TOKEN": "ghp_secret",
            "AWS_SECRET_ACCESS_KEY": "aws-secret",
            "CLAUDECODE": "1",
            "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
            "RANDOM_PARENT_VAR": "should-not-leak",
        }
        with patch.dict("os.environ", fake_env, clear=True):
            scrubbed = _scrubbed_child_env(extra={"AGY_GUARD_MODE": "strict"})

        assert scrubbed == {
            "PATH": "/usr/bin",
            "HOME": "/home/testuser",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "AGY_GUARD_MODE": "strict",
        }

    def test_parse_model_map_csv_and_json(self):
        assert _parse_model_map(None) == {}
        assert _parse_model_map("  ") == {}
        assert _parse_model_map("a=x, B = y ") == {"a": "x", "b": "y"}
        assert _parse_model_map('{"~google/gemini-pro-latest": "gemini-custom"}') == {
            "~google/gemini-pro-latest": "gemini-custom"
        }
        assert _parse_model_map("{bad json") == {}

    def test_quota_gate_passes_on_zero_with_devnull_and_scrubbed_env(self):
        captured: dict = {}
        with (
            patch(
                "council.providers.cli_sub.subprocess.Popen",
                side_effect=_mock_popen_factory(0, "ok\n", "", capture=captured),
            ),
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "secret-or-key"}),
        ):
            _check_quota_gate("quota-ok --check", "agy-cli", "gemini-4-argon-high")

        assert captured["cmd"] == ["quota-ok", "--check"]
        assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
        assert captured["kwargs"]["start_new_session"] is True
        assert "OPENROUTER_API_KEY" not in captured["kwargs"]["env"]

    def test_quota_gate_raises_rate_limit_on_nonzero(self):
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(2, "weekly reserve reached\n", ""),
        ):
            with pytest.raises(RateLimitError) as exc_info:
                _check_quota_gate("quota-check", "claude-cli", "sonnet")
        assert "weekly reserve reached" in str(exc_info.value)

    def test_quota_gate_missing_command_raises_provider_error(self):
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(side_effect=FileNotFoundError("no such binary")),
        ):
            with pytest.raises(LLMProviderError) as exc_info:
                _check_quota_gate("missing-gate-bin", "agy-cli", "gemini-4-argon-high")
        assert "quota command not found" in str(exc_info.value)


class TestAgyCliProvider:
    """Tests for AgyCliProvider resolution, lockdown settings, stdin delivery, and errors."""

    def test_is_enabled_and_defaults(self):
        with patch.dict("os.environ", {"COUNCIL_AGY_CLI": "1"}, clear=True):
            assert AgyCliProvider.is_enabled() is True
            provider = AgyCliProvider()
            assert provider.pro_model == "gemini-4-argon-high"
            assert provider.flash_model == "gemini-3.8-flash-high"
        with patch.dict("os.environ", {"COUNCIL_AGY_CLI": "0"}):
            assert AgyCliProvider.is_enabled() is False

    def test_resolve_strict_known_aliases_only(self):
        with patch.dict(
            "os.environ",
            {
                "COUNCIL_AGY_PRO_MODEL": "gemini-pro-sub",
                "COUNCIL_AGY_FLASH_MODEL": "gemini-flash-sub",
                "COUNCIL_AGY_MODEL_MAP": "google/gemini-custom=gemini-4-argon-low",
            },
        ):
            provider = AgyCliProvider()

        assert provider.resolve("~google/gemini-pro-latest") == "gemini-pro-sub"
        assert provider.resolve("gemini-pro") == "gemini-pro-sub"
        assert provider.resolve("~google/gemini-flash-latest") == "gemini-flash-sub"
        assert provider.resolve("gemini-flash") == "gemini-flash-sub"
        assert provider.resolve("google/gemini-4-argon-high") == "gemini-4-argon-high"
        assert provider.resolve("gemini-3.8-flash-high") == "gemini-3.8-flash-high"
        assert provider.resolve("google/gemini-custom") == "gemini-4-argon-low"
        # Unknown/older Gemini versions and Gemma are NOT silently substituted
        assert provider.resolve("google/gemini-2.5-flash") is None
        assert provider.resolve("google/gemma-4-31b-it") is None
        assert provider.resolve("google/--bad-flag") is None
        assert provider.resolve("google/gemini-pro-latest:free") is None
        assert provider.resolve("~openai/gpt-sol-latest") is None

    def test_generate_missing_dash_nul_and_missing_binary(self):
        provider = AgyCliProvider(binary="nonexistent-agy-bin")
        with pytest.raises(ModelNotFoundError):
            provider.generate("Hello", model=None)
        with pytest.raises(ModelNotFoundError):
            provider.generate("Hello", model="--injected-flag")
        with pytest.raises(LLMProviderError) as nul_exc:
            provider.generate("bad\x00prompt", model="gemini-4-argon-high")
        assert "NUL byte" in str(nul_exc.value)
        for blank in ("", "   \n\t"):
            with pytest.raises(LLMProviderError, match="Prompt must not be empty"):
                provider.generate(blank, model="gemini-4-argon-high")
        with patch("council.providers.cli_sub.shutil.which", return_value=None):
            with pytest.raises(AuthenticationError):
                provider.generate("Hello", model="gemini-4-argon-high")

    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/agy")
    def test_generate_large_prompt_via_stdin_and_strict_lockdown(self, _mock_which):
        captured: dict = {}
        payload = {
            "status": "SUCCESS",
            "response": "Structured Gemini answer",
            "model": "gemini-4-argon-high",
            "finished_reason": "stop",
            "conversation_id": "conv-123",
        }
        large_prompt = "--help " + ("x" * 200_000)

        with (
            patch(
                "council.providers.cli_sub.subprocess.Popen",
                side_effect=_mock_popen_factory(0, json.dumps(payload), "", capture=captured),
            ),
            patch.dict(
                "os.environ",
                {"OPENROUTER_API_KEY": "or-secret", "GEMINI_API_KEY": "gem-secret"},
            ),
        ):
            provider = AgyCliProvider(timeout=90.0, quota_cmd="")
            resp = provider.generate(large_prompt, model="gemini-4-argon-high")

        assert resp.content == "Structured Gemini answer"
        assert resp.model == "google/gemini-4-argon-high"
        # Prompt goes over stdin, never argv
        assert captured["stdin_text"] == large_prompt
        assert all(len(arg) < 1024 for arg in captured["cmd"])
        assert "--input-format" in captured["cmd"]
        assert "--sandbox" in captured["cmd"]
        assert "--disable-slash-commands" in captured["cmd"]
        assert "OPENROUTER_API_KEY" not in captured["kwargs"]["env"]
        assert "GEMINI_API_KEY" not in captured["kwargs"]["env"]
        assert captured["kwargs"]["env"]["AGY_GUARD_MODE"] == "strict"

        settings = captured["settings"]
        assert settings["toolPermission"] == "request-review"
        assert settings["allowNonWorkspaceAccess"] is False
        assert settings["agentMode"] == ""
        assert settings["permissions"]["allow"] == []
        for denied in (
            "read_file",
            "view_file",
            "read_url_content",
            "browser_subagent",
            "search_web",
            "mcp_*",
            "mcp__*",
        ):
            assert denied in settings["permissions"]["deny"]

    @patch("council.providers.cli_sub.os.killpg")
    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/agy")
    def test_generate_subprocess_timeout_kills_pgroup_and_raises_cli_timeout(
        self, _mock_which, mock_killpg
    ):
        timeout_exc = subprocess.TimeoutExpired(cmd=["agy"], timeout=35.0)
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(side_effect=timeout_exc),
        ):
            provider = AgyCliProvider(timeout=30.0, quota_cmd="")
            with pytest.raises(CLITimeoutError) as exc_info:
                provider.generate("Slow prompt", model="gemini-4-argon-high")

        assert exc_info.value.is_retryable is False
        mock_killpg.assert_called_once_with(42424, signal.SIGKILL)

    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/agy")
    def test_generate_print_timeout_denied_empty_and_non_json_errors(self, _mock_which):
        provider = AgyCliProvider(timeout=30.0, quota_cmd="")

        # print_timeout -> CLITimeoutError (non-retryable, no OpenRouter fallback)
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(
                0,
                json.dumps(
                    {"status": "SUCCESS", "response": "partial", "finished_reason": "print_timeout"}
                ),
                "",
            ),
        ):
            with pytest.raises(CLITimeoutError):
                provider.generate("Slow", model="gemini-4-argon-high")

        # denied_actions -> LLMProviderError
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(
                0,
                json.dumps(
                    {"status": "SUCCESS", "response": "ok", "denied_actions": ["command(ls)"]}
                ),
                "",
            ),
        ):
            with pytest.raises(LLMProviderError, match="denied tool action"):
                provider.generate("Prompt", model="gemini-4-argon-high")

        # empty stdout
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(1, "   ", "boom"),
        ):
            with pytest.raises(LLMProviderError, match="empty output"):
                provider.generate("Prompt", model="gemini-4-argon-high")

        # non-JSON stdout
        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(0, "not-json-at-all", ""),
        ):
            with pytest.raises(LLMProviderError, match="non-JSON output"):
                provider.generate("Prompt", model="gemini-4-argon-high")


class TestClaudeCliProvider:
    """Tests for ClaudeCliProvider resolution, stdin delivery, and error handling."""

    def test_resolve_strict_anthropic_models(self):
        provider = ClaudeCliProvider()
        assert provider.resolve("~anthropic/claude-sonnet-latest") == "sonnet"
        assert provider.resolve("claude-opus") == "opus"
        assert provider.resolve("claude-haiku-latest") == "haiku"
        # Explicit versioned IDs pass through without silent alias substitution
        assert provider.resolve("anthropic/claude-sonnet-4-6") == "claude-sonnet-4-6"
        assert provider.resolve("claude-opus-4-6") == "claude-opus-4-6"
        assert provider.resolve("anthropic/--bad-flag") is None
        assert provider.resolve("anthropic/claude-sonnet:beta") is None
        assert provider.resolve("google/gemini-2.5-pro") is None

    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/claude")
    def test_generate_stdin_prompt_env_allowlist_and_reported_model(self, _mock_which):
        captured: dict = {}
        payload = {
            "is_error": False,
            "result": "Claude CLI reply",
            "modelUsage": {"claude-sonnet-4-6": {"inputTokens": 12, "outputTokens": 8}},
        }
        large_prompt = "- bullet leading " + ("y" * 200_000)

        with (
            patch(
                "council.providers.cli_sub.subprocess.Popen",
                side_effect=_mock_popen_factory(0, json.dumps(payload), "", capture=captured),
            ),
            patch.dict(
                "os.environ",
                {
                    "PATH": "/usr/bin",
                    "HOME": "/home/testuser",
                    "CLAUDECODE": "1",
                    "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
                    "ANTHROPIC_AUTH_TOKEN": "zai-tok",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3",
                    "OPENROUTER_API_KEY": "or-secret",
                    "UNLISTED_VAR": "dropped",
                },
                clear=True,
            ),
        ):
            provider = ClaudeCliProvider(timeout=60.0, quota_cmd="")
            resp = provider.generate(large_prompt, model="sonnet")

        assert resp.content == "Claude CLI reply"
        assert resp.model == "anthropic/claude-sonnet-4-6"
        assert captured["stdin_text"] == large_prompt
        cmd = captured["cmd"]
        assert "--input-format" in cmd
        assert "--strict-mcp-config" in cmd
        assert "--safe-mode" in cmd
        assert "--disable-slash-commands" in cmd
        assert "--no-session-persistence" in cmd
        assert captured["mcp"] == {"mcpServers": {}}
        assert all(len(arg) < 1024 for arg in cmd)

        env = captured["kwargs"]["env"]
        assert set(env.keys()) <= {"PATH", "HOME"}

    @patch("council.providers.cli_sub.shutil.which", return_value="/usr/local/bin/claude")
    def test_generate_rate_limit_timeout_and_non_json(self, _mock_which):
        provider = ClaudeCliProvider(timeout=45.0, quota_cmd="")

        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(
                1, json.dumps({"is_error": True, "result": "Usage limit reached (429)"}), ""
            ),
        ):
            with pytest.raises(RateLimitError):
                provider.generate("Prompt", model="sonnet")

        with (
            patch("council.providers.cli_sub.os.killpg"),
            patch(
                "council.providers.cli_sub.subprocess.Popen",
                side_effect=_mock_popen_factory(
                    side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=45.0)
                ),
            ),
        ):
            with pytest.raises(CLITimeoutError):
                provider.generate("Prompt", model="sonnet")

        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(0, "broken-json", ""),
        ):
            with pytest.raises(LLMProviderError, match="non-JSON output"):
                provider.generate("Prompt", model="sonnet")

        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(1, "   ", "cli crashed"),
        ):
            with pytest.raises(LLMProviderError, match="empty output"):
                provider.generate("Prompt", model="sonnet")

        with patch(
            "council.providers.cli_sub.subprocess.Popen",
            side_effect=_mock_popen_factory(side_effect=PermissionError("permission denied")),
        ):
            with pytest.raises(LLMProviderError, match="failed to execute CLI"):
                provider.generate("Prompt", model="sonnet")

        for blank in ("", "  \n"):
            with pytest.raises(LLMProviderError, match="Prompt must not be empty"):
                provider.generate(blank, model="sonnet")

    def test_generate_missing_binary_and_flag_model_errors(self):
        provider = ClaudeCliProvider(binary="nonexistent-claude-bin", quota_cmd="")
        with pytest.raises(ModelNotFoundError):
            provider.generate("Prompt", model="--bad-flag")
        with patch("council.providers.cli_sub.shutil.which", return_value=None):
            with pytest.raises(AuthenticationError):
                provider.generate("Prompt", model="sonnet")
