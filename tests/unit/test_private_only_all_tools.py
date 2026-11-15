"""End-to-end unit tests for private_only across all Council MCP tools and sessions."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from council.core.orchestrator import ConversationOrchestrator
from council.core.registry import ToolRegistry
from council.services.cache import ResponseCache
from council.services.session_manager import SessionManager


def _make_orchestrator(
    active_model: str = "~openai/gpt-sol-latest",
) -> tuple[ConversationOrchestrator, Mock]:
    registry = ToolRegistry()
    registry.discover_tools()
    mgr = Mock()
    mgr.active_model = active_model
    mgr.generate_content.return_value = ("Mock answer", "openai/gpt-5")
    return ConversationOrchestrator(registry, mgr, cache=ResponseCache()), mgr


class TestPrivateOnlyAcrossAllTools:
    """Verify H3: every LLM-calling tool honours private_only and others reject it."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "params"),
        [
            ("ask", {"question": "Summarize architecture"}),
            ("code_review", {"code": "def f(): return 1"}),
            ("debug", {"error_message": "KeyError: 'x'", "code_context": "d = {}\nd['x']"}),
            ("refactor", {"code": "x = 1\ny = 2", "goal": "simplify_logic"}),
            ("explain", {"topic": "raft consensus"}),
            ("brainstorm", {"topic": "caching strategies"}),
            ("test_cases", {"code_or_feature": "login handler"}),
            (
                "synthesize_perspectives",
                {
                    "topic": "DB choice",
                    "perspectives": [{"content": "SQL"}, {"content": "KV"}],
                },
            ),
        ],
    )
    async def test_answer_tools_forward_private_only_and_validate_bool(self, tool_name, params):
        orchestrator, mgr = _make_orchestrator()

        with patch("council._server_instance", SimpleNamespace(model_manager=mgr)):
            bad = await orchestrator.execute_tool(tool_name, {**params, "private_only": "yes"})
            assert bad.success is False
            assert "boolean" in (bad.error or "")

            ok = await orchestrator.execute_tool(tool_name, {**params, "private_only": True})
            assert ok.success is True
            assert mgr.generate_content.call_args[1].get("private_only") is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name",
        [
            "list_models",
            "set_model",
            "recommend_model",
            "server_info",
            "list_conversations",
            "end_conversation",
            "get_conversation_history",
        ],
    )
    async def test_non_private_capable_tools_reject_private_only_flag(self, tool_name):
        orchestrator, _mgr = _make_orchestrator()

        res = await orchestrator.execute_tool(tool_name, {"private_only": True})
        assert res.success is False
        assert f"Tool '{tool_name}' does not accept 'private_only'" in (res.error or "")

    @pytest.mark.asyncio
    async def test_cache_keys_isolate_private_only_from_non_private(self):
        orchestrator, mgr = _make_orchestrator()

        with patch("council._server_instance", SimpleNamespace(model_manager=mgr)):
            await orchestrator.execute_tool("ask", {"question": "Same question"})
            await orchestrator.execute_tool(
                "ask", {"question": "Same question", "private_only": True}
            )

        assert mgr.generate_content.call_count == 2
        assert mgr.generate_content.call_args_list[0][1].get("private_only") is None
        assert mgr.generate_content.call_args_list[1][1].get("private_only") is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_value", ["false", "true", 0, 1, None, ["true"]])
    async def test_orchestrator_rejects_non_boolean_private_only_before_cache_lookup(
        self, bad_value
    ):
        orchestrator, mgr = _make_orchestrator()
        orchestrator.cache.get = Mock(return_value=None)

        res = await orchestrator.execute_tool(
            "ask", {"question": "Cached?", "private_only": bad_value}
        )
        assert res.success is False
        assert res.error == "private_only must be a boolean"
        orchestrator.cache.get.assert_not_called()
        mgr.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_conversation_sessions_enforce_and_persist_private_only(self):
        orchestrator, mgr = _make_orchestrator()
        fresh_sm = SessionManager()

        with (
            patch("council._server_instance", SimpleNamespace(model_manager=mgr)),
            patch("council.tools.conversation._session_manager", fresh_sm),
        ):
            # Disallowed model rejected at start_conversation when private_only=True
            denied = await orchestrator.execute_tool(
                "start_conversation",
                {"model": "~moonshotai/kimi-latest", "private_only": True},
            )
            assert denied.success is False
            assert "private_only=True" in (denied.error or "")

            # Allowed model creates sticky private_only session
            started = await orchestrator.execute_tool(
                "start_conversation",
                {
                    "model": "~z-ai/glm-latest",
                    "initial_message": "First private turn",
                    "private_only": True,
                },
            )
            assert started.success is True
            assert mgr.generate_content.call_args[1].get("private_only") is True

            sess_id = next(iter(fresh_sm.sessions.keys()))
            mgr.generate_content.reset_mock()

            # Follow-up continue_conversation WITHOUT private_only stays private_only!
            cont = await orchestrator.execute_tool(
                "continue_conversation",
                {"session_id": sess_id, "message": "Second turn"},
            )
            assert cont.success is True
            assert mgr.generate_content.call_args[1].get("private_only") is True

            # Non-private session cannot be continued with private_only=True if model is excluded
            non_priv_id = fresh_sm.create_session(model="~moonshotai/kimi-latest")
            blocked_cont = await orchestrator.execute_tool(
                "continue_conversation",
                {"session_id": non_priv_id, "message": "Leak?", "private_only": True},
            )
            assert blocked_cont.success is False
            assert "private_only=True" in (blocked_cont.error or "")

    @pytest.mark.asyncio
    async def test_start_conversation_fails_closed_and_cleans_session_on_initial_send_error(self):
        orchestrator, mgr = _make_orchestrator()
        fresh_sm = SessionManager()
        mgr.generate_content.side_effect = RuntimeError("provider unavailable")

        with (
            patch("council._server_instance", SimpleNamespace(model_manager=mgr)),
            patch("council.tools.conversation._session_manager", fresh_sm),
        ):
            failed = await orchestrator.execute_tool(
                "start_conversation",
                {
                    "model": "~openai/gpt-sol-latest",
                    "initial_message": "Hi",
                    "private_only": True,
                },
            )
            assert failed.success is False
            assert fresh_sm.sessions == {}

        # Also fails closed if model_manager is None when initial_message is supplied
        with (
            patch("council._server_instance", SimpleNamespace(model_manager=None)),
            patch("council.tools.conversation._session_manager", fresh_sm),
        ):
            no_mgr = await orchestrator.execute_tool(
                "start_conversation",
                {
                    "model": "~openai/gpt-sol-latest",
                    "initial_message": "Hi",
                    "private_only": True,
                },
            )
            assert no_mgr.success is False
            assert fresh_sm.sessions == {}

    @pytest.mark.asyncio
    async def test_debug_session_inherits_private_only_and_fails_closed_on_evicted_or_non_private(
        self,
    ):
        orchestrator, mgr = _make_orchestrator()
        fresh_sm = SessionManager()

        with (
            patch("council._server_instance", SimpleNamespace(model_manager=mgr)),
            patch("council.tools.conversation._session_manager", fresh_sm),
        ):
            # Missing / evicted session_id fails closed
            missing = await orchestrator.execute_tool(
                "debug",
                {
                    "error_message": "ValueError: bad",
                    "code_context": "x = int('a')",
                    "session_id": "evicted-sess-999",
                },
            )
            assert missing.success is False
            assert "not found" in (missing.error or "")
            mgr.generate_content.assert_not_called()

            # Private session automatically propagates private_only=True and session.model
            priv_id = fresh_sm.create_session(model="~z-ai/glm-latest", private_only=True)
            ok = await orchestrator.execute_tool(
                "debug",
                {
                    "error_message": "TypeError: boom",
                    "code_context": "1 + 'a'",
                    "session_id": priv_id,
                },
            )
            assert ok.success is True
            assert mgr.generate_content.call_args[1].get("private_only") is True
            assert mgr.generate_content.call_args[1].get("model") == "~z-ai/glm-latest"

            # Non-private session model rejected when debug called with private_only=True
            mgr.generate_content.reset_mock()
            non_priv_id = fresh_sm.create_session(model="~moonshotai/kimi-latest")
            rejected = await orchestrator.execute_tool(
                "debug",
                {
                    "error_message": "RuntimeError: leak?",
                    "code_context": "raise RuntimeError()",
                    "session_id": non_priv_id,
                    "private_only": True,
                },
            )
            assert rejected.success is False
            assert "private_only=True" in (rejected.error or "")
            mgr.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_cli_alias_aligned_across_session_and_debug(self):
        orchestrator, mgr = _make_orchestrator()
        mgr.is_private_allowed_model = lambda m: m == "custom-gemini-alias"
        fresh_sm = SessionManager()

        with (
            patch("council._server_instance", SimpleNamespace(model_manager=mgr)),
            patch("council.tools.conversation._session_manager", fresh_sm),
        ):
            started = await orchestrator.execute_tool(
                "start_conversation",
                {
                    "model": "custom-gemini-alias",
                    "initial_message": "Hello via CLI alias",
                    "private_only": True,
                },
            )
            assert started.success is True
            sess_id = next(iter(fresh_sm.sessions.keys()))

            cont = await orchestrator.execute_tool(
                "continue_conversation",
                {"session_id": sess_id, "message": "Follow-up"},
            )
            assert cont.success is True

            dbg = await orchestrator.execute_tool(
                "debug",
                {
                    "error_message": "AssertionError",
                    "code_context": "assert False",
                    "session_id": sess_id,
                },
            )
            assert dbg.success is True
            assert mgr.generate_content.call_args[1].get("model") == "custom-gemini-alias"
            assert mgr.generate_content.call_args[1].get("private_only") is True
