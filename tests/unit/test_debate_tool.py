"""Tests for the debate tool."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from council.providers.base import RateLimitError
from council.tools.debate import DEFAULT_PANEL, DebateTool


def replying_manager(fail_models=(), delay=0.0, fail_rebuttals=(), empty_models=()):
    """A manager whose reply names the model and prompt kind; some models fail.

    It also records the most calls it had in flight at once.
    """
    manager = Mock()
    lock = threading.Lock()
    manager.prompts = []
    manager.in_flight = 0
    manager.peak_in_flight = 0

    def generate_content(prompt, model=None):
        with lock:
            manager.prompts.append((model, prompt))
            manager.in_flight += 1
            manager.peak_in_flight = max(manager.peak_in_flight, manager.in_flight)
        try:
            if delay:
                time.sleep(delay)
            kind = (
                "synthesis"
                if "judging" in prompt
                else "rebuttal"
                if "Respond" in prompt
                else "open"
            )
            if model in fail_models or (kind == "rebuttal" and model in fail_rebuttals):
                raise RateLimitError("busy or rate limited", "openrouter", model)
            if model in empty_models:
                return "", f"{model} (served)"
            return f"{kind} by {model}", f"{model} (served)"
        finally:
            with lock:
                manager.in_flight -= 1

    manager.generate_content.side_effect = generate_content
    return manager


@pytest.fixture
def manager():
    """A manager where every model answers."""
    return replying_manager()


@pytest.fixture
def server(manager):
    """Install a fake server instance exposing model_manager."""
    with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
        yield


def prompts_to(manager, model):
    """The prompts sent to one model, in order."""
    return [prompt for m, prompt in manager.prompts if m == model]


class TestDebateValidation:
    """Input checks, all before any model call."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "parameters,message",
        [
            ({}, "Topic is required"),
            ({"topic": "  "}, "Topic is required"),
            ({"topic": "x", "positions": ["only one"]}, "needs 2-4 debaters; got 1 positions"),
            ({"topic": "x", "positions": list("abcde")}, "needs 2-4 debaters; got 5 positions"),
            ({"topic": "x", "models": ["~z-ai/glm-latest"]}, "needs 2-4 debaters; got 1 models"),
            ({"topic": "x", "positions": ["a", ""]}, "positions must be a list"),
            ({"topic": "x", "models": "~z-ai/glm-latest"}, "models must be a list"),
            ({"topic": "x", "rounds": 3}, "rounds must be 1 or 2"),
            (
                {"topic": "x", "positions": ["a", "b"], "models": ["m1", "m2", "m3"]},
                "3 models for 2 positions would leave models out",
            ),
            ({"topic": "x", "rounds": True}, "rounds must be 1 or 2"),
        ],
    )
    async def test_bad_input_is_rejected(self, server, manager, parameters, message):
        """Bad input fails with a clear message and costs no calls."""
        result = await DebateTool().execute(parameters)
        assert result.success is False
        assert message in result.error
        manager.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_manager_unavailable(self):
        """With no server instance and no bundled global, the tool reports it."""
        with patch("council._server_instance", None):
            result = await DebateTool().execute({"topic": "x"})
        assert result.success is False
        assert result.error == "Model manager not available"


class TestDebateRun:
    """The rounds, the transcript and the call count."""

    @pytest.mark.asyncio
    async def test_default_panel_two_rounds(self, server, manager):
        """With no models given, the three-family panel debates: 3 + 3 + 1 calls."""
        result = await DebateTool().execute({"topic": "Monorepo or polyrepo?"})

        assert result.success is True
        assert manager.generate_content.call_count == 7
        for model in DEFAULT_PANEL:
            assert f"open by {model}" in result.result
            assert f"rebuttal by {model}" in result.result
        assert "## Synthesis\n\nsynthesis by None" in result.result
        assert result.result.endswith("[Debate: 3 debaters, 2 rounds, 7 calls]")

    @pytest.mark.asyncio
    async def test_positions_are_assigned_and_models_cycle(self, server, manager):
        """Debater i argues positions[i] on models[i % len(models)]."""
        await DebateTool().execute(
            {
                "topic": "Database",
                "positions": ["Postgres", "SQLite", "DuckDB"],
                "models": ["~z-ai/glm-latest", "~moonshotai/kimi-latest"],
                "rounds": 1,
            }
        )

        glm = prompts_to(manager, "~z-ai/glm-latest")
        kimi = prompts_to(manager, "~moonshotai/kimi-latest")
        assert len(glm) == 2 and len(kimi) == 1
        assert any("Argue for this position: Postgres" in p for p in glm)
        assert any("Argue for this position: DuckDB" in p for p in glm)
        assert "Argue for this position: SQLite" in kimi[0]

    @pytest.mark.asyncio
    async def test_multiline_stance_keeps_its_heading_on_one_line(self, server, manager):
        """A stance with newlines is flattened so the transcript heading stays intact."""
        result = await DebateTool().execute(
            {"topic": "x", "positions": ["Use\nPostgres", "SQLite"], "rounds": 1}
        )
        assert "### Debater 1: Use Postgres" in result.result

    @pytest.mark.asyncio
    async def test_without_positions_each_model_gives_its_own_view(self, server, manager):
        """Panel mode asks for each model's own answer, not an assigned stance."""
        await DebateTool().execute({"topic": "Tabs or spaces?", "rounds": 1})
        opening = prompts_to(manager, DEFAULT_PANEL[0])[0]
        assert "Give your own answer" in opening
        assert "Argue for this position" not in opening

    @pytest.mark.asyncio
    async def test_rebuttal_sees_the_other_openings_not_its_own_as_others(self, server, manager):
        """Each rebuttal prompt carries the other debaters' openings."""
        await DebateTool().execute(
            {"topic": "x", "models": ["~z-ai/glm-latest", "~moonshotai/kimi-latest"]}
        )
        glm_rebuttal = prompts_to(manager, "~z-ai/glm-latest")[1]
        others = glm_rebuttal.split("The other debaters said:")[1]
        assert "open by ~moonshotai/kimi-latest" in others
        assert "open by ~z-ai/glm-latest" not in others

    @pytest.mark.asyncio
    async def test_one_round_skips_rebuttals(self, server, manager):
        """rounds=1 is openings plus synthesis only."""
        result = await DebateTool().execute({"topic": "x", "rounds": 1})
        assert manager.generate_content.call_count == 4
        assert "Rebuttals" not in result.result
        assert result.result.endswith("[Debate: 3 debaters, 1 round, 4 calls]")

    @pytest.mark.asyncio
    async def test_synthesis_goes_to_the_synthesis_model_with_the_transcript(self, server, manager):
        """The synthesis model gets every opening and rebuttal."""
        await DebateTool().execute(
            {
                "topic": "x",
                "models": ["~z-ai/glm-latest", "~moonshotai/kimi-latest"],
                "synthesis_model": "~openai/gpt-sol-latest",
            }
        )
        synthesis = prompts_to(manager, "~openai/gpt-sol-latest")
        assert len(synthesis) == 1
        for text in ("open by ~z-ai/glm-latest", "rebuttal by ~moonshotai/kimi-latest"):
            assert text in synthesis[0]

    @pytest.mark.asyncio
    async def test_transcript_names_the_served_model(self, server, manager):
        """Each turn is labelled with the model that actually answered."""
        result = await DebateTool().execute({"topic": "x", "rounds": 1})
        assert "*[Model: ~z-ai/glm-latest (served)]*" in result.result

    @pytest.mark.asyncio
    async def test_openings_run_concurrently(self):
        """All three openings are in flight at the same time."""
        slow = replying_manager(delay=0.1)
        with patch("council._server_instance", SimpleNamespace(model_manager=slow)):
            result = await DebateTool().execute({"topic": "x", "rounds": 1})

        assert result.success is True
        assert slow.peak_in_flight == 3


class TestDebateFailures:
    """A failing debater or synthesis."""

    @pytest.mark.asyncio
    async def test_failed_debater_is_noted_and_dropped(self):
        """A debater that fails its opening is reported and sits out the rebuttals."""
        manager = replying_manager(fail_models={"~moonshotai/kimi-latest"})
        with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
            result = await DebateTool().execute({"topic": "x"})

        assert result.success is True
        assert "⚠️ ~moonshotai/kimi-latest failed: busy or rate limited" in result.result
        assert len(prompts_to(manager, "~moonshotai/kimi-latest")) == 1
        assert result.result.endswith("[Debate: 3 debaters, 2 rounds, 6 calls]")
        assert result.metadata["cacheable"] is False

    @pytest.mark.asyncio
    async def test_too_few_answers_is_an_error(self):
        """With fewer than two openings there is no debate."""
        manager = replying_manager(fail_models={"~z-ai/glm-latest", "~moonshotai/kimi-latest"})
        with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
            result = await DebateTool().execute({"topic": "x"})

        assert result.success is False
        assert "Too few debaters answered" in result.error
        assert "~moonshotai/kimi-latest" in result.error

    @pytest.mark.asyncio
    async def test_failed_synthesis_keeps_the_transcript(self):
        """If the synthesis fails the debate itself is still returned."""
        manager = replying_manager(fail_models={"~openai/gpt-luna-latest"})
        with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
            result = await DebateTool().execute(
                {"topic": "x", "rounds": 1, "synthesis_model": "~openai/gpt-luna-latest"}
            )

        assert result.success is True
        assert "open by ~z-ai/glm-latest" in result.result
        assert "⚠️ The synthesis failed: busy or rate limited" in result.result
        assert result.metadata["cacheable"] is False

    @pytest.mark.asyncio
    async def test_empty_reply_counts_as_a_failure(self):
        """A blank opening is reported, sits out later rounds, and vetoes caching."""
        manager = replying_manager(empty_models={"~moonshotai/kimi-latest"})
        with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
            result = await DebateTool().execute({"topic": "x"})

        assert result.success is True
        assert "⚠️ ~moonshotai/kimi-latest failed: empty reply" in result.result
        assert len(prompts_to(manager, "~moonshotai/kimi-latest")) == 1
        assert result.metadata["cacheable"] is False

    @pytest.mark.asyncio
    async def test_failed_rebuttal_is_noted_and_vetoes_caching(self):
        """A rebuttal that fails after a good opening marks the debate incomplete."""
        manager = replying_manager(fail_rebuttals={"~z-ai/glm-latest"})
        with patch("council._server_instance", SimpleNamespace(model_manager=manager)):
            result = await DebateTool().execute({"topic": "x"})

        assert result.success is True
        assert "open by ~z-ai/glm-latest" in result.result
        assert "⚠️ ~z-ai/glm-latest failed: busy or rate limited" in result.result
        assert result.metadata["cacheable"] is False

    @pytest.mark.asyncio
    async def test_complete_debate_stays_cacheable(self, server, manager):
        """A debate where every call answered carries no cache veto."""
        result = await DebateTool().execute({"topic": "x", "rounds": 1})
        assert "cacheable" not in result.metadata
