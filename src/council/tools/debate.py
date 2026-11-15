"""Debate tool: several models argue a topic, rebut each other, and one synthesizes."""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from ..providers.cli_sub import is_excluded_model, is_non_private_model
from .base import (
    PRIVATE_ONLY_DESCRIPTION,
    MCPTool,
    ToolOutput,
    get_model_manager,
    parse_private_only,
    report_progress,
)

logger = logging.getLogger(__name__)

# Three families, so the debate isn't one model agreeing with itself.
# GLM runs on the flat-rate Z.ai plan when its key is set (unless private_only=True).
DEFAULT_PANEL = ["~openai/gpt-sol-latest", "~z-ai/glm-latest", "~moonshotai/kimi-latest"]
PRIVATE_DEFAULT_PANEL = [
    "~openai/gpt-sol-latest",
    "~google/gemini-pro-latest",
    "mistralai/mistral-medium-3-5",
]
PRIVATE_SYNTHESIS_FALLBACKS = (
    "~anthropic/claude-sonnet-latest",
    "~openai/gpt-sol-latest",
    "~google/gemini-pro-latest",
    "mistralai/mistral-medium-3-5",
)
MIN_DEBATERS = 2
MAX_DEBATERS = 4
MAX_CRITERIA = 8
ERROR_PREVIEW_CHARS = 200
_MARKDOWN_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$", re.M)


@dataclass
class Debater:
    """One seat in the debate: a model, and the stance it argues if one was assigned."""

    number: int
    model: str
    stance: str | None
    opening: str | None = None
    rebuttal: str | None = None

    @property
    def title(self) -> str:
        """Heading for this debater's turns."""
        if self.stance:
            return f"Debater {self.number}: {self.stance}"
        return f"Debater {self.number}"


@dataclass
class Turn:
    """The result of one model call."""

    text: str | None
    model_used: str
    error: str | None = None


class DebateTool(MCPTool):
    """Run a structured debate between models, then synthesize it."""

    @property
    def name(self) -> str:
        return "debate"

    @property
    def description(self) -> str:
        return (
            "Have 2-4 models debate a topic: opening statements, then rebuttals, then a "
            "synthesis of where they agree, where they really disagree, and a recommendation. "
            "Assign stances with `positions`, or leave them out to get each model's own view. "
            "Default panel: GPT, GLM and Kimi (or GPT, Gemini and Mistral when "
            "`private_only=true`). Makes one call per debater per round, plus one; each round "
            "waits for its slowest model, so a debate with reasoning models can take minutes."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The question or decision to debate",
                },
                "positions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": MIN_DEBATERS,
                    "maxItems": MAX_DEBATERS,
                    "description": (
                        "Stances to argue, one per debater (e.g. ['Use Postgres', "
                        "'Use SQLite']). Omit to have each model give its own view"
                    ),
                },
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": MAX_DEBATERS,
                    "description": (
                        "Debater models. With positions, debater i uses models[i % len]. "
                        f"Default: {', '.join(DEFAULT_PANEL)} "
                        f"(private_only default: {', '.join(PRIVATE_DEFAULT_PANEL)})"
                    ),
                },
                "synthesis_model": {
                    "type": "string",
                    "description": "Model that writes the synthesis (default: the active model)",
                },
                "rounds": {
                    "type": "integer",
                    "enum": [1, 2],
                    "default": 2,
                    "description": "1 = opening statements only; 2 = openings and rebuttals",
                },
                "criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": MAX_CRITERIA,
                    "description": (
                        "Optional decision criteria (1-8 items, e.g. ['latency', "
                        "'maintainability', 'security']) requested in a Markdown synthesis "
                        "decision table and checked before caching"
                    ),
                },
                "private_only": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        f"{PRIVATE_ONLY_DESCRIPTION}; also switches the default panel to "
                        f"{', '.join(PRIVATE_DEFAULT_PANEL)}"
                    ),
                },
            },
            "required": ["topic"],
        }

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """The answer depends only on the input and the models."""
        return True

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            raw_priv, priv_err = parse_private_only(parameters)
            if priv_err:
                return ToolOutput(success=False, error=priv_err)

            criteria_or_error = self._parse_criteria(parameters)
            if isinstance(criteria_or_error, str):
                return ToolOutput(success=False, error=criteria_or_error)

            debaters_or_error = self._seat_debaters(parameters, private_only=raw_priv)
            if isinstance(debaters_or_error, str):
                return ToolOutput(success=False, error=debaters_or_error)
            debaters = debaters_or_error

            synth_model = parameters.get("synthesis_model")
            if synth_model is not None and (
                not isinstance(synth_model, str) or not synth_model.strip()
            ):
                return ToolOutput(success=False, error="synthesis_model must be a non-empty string")
            if isinstance(synth_model, str) and is_excluded_model(synth_model):
                return ToolOutput(
                    success=False,
                    error=f"synthesis_model '{synth_model}' is excluded by policy",
                )
            if raw_priv and isinstance(synth_model, str) and is_non_private_model(synth_model):
                return ToolOutput(
                    success=False,
                    error=f"synthesis_model '{synth_model}' is excluded when private_only=True",
                )

            topic = parameters["topic"].strip()
            rounds = parameters.get("rounds", 2)
            if isinstance(rounds, bool) or rounds not in (1, 2):
                return ToolOutput(success=False, error="rounds must be 1 or 2")

            model_manager = get_model_manager()
            if not model_manager:
                return ToolOutput(success=False, error="Model manager not available")

            return await self._run(
                model_manager,
                topic,
                debaters,
                rounds,
                parameters,
                criteria=criteria_or_error,
                private_only=raw_priv,
                synthesis_model=synth_model,
            )
        except Exception as e:
            logger.error(f"Debate error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    @staticmethod
    def _parse_criteria(parameters: dict[str, Any]) -> list[str] | str:
        """Validate optional criteria list (1-8 non-empty strings)."""
        raw = parameters.get("criteria")
        if raw is None:
            return []
        if (
            not isinstance(raw, list)
            or not (1 <= len(raw) <= MAX_CRITERIA)
            or not all(isinstance(c, str) and c.strip() for c in raw)
        ):
            return f"criteria must be a list of 1-{MAX_CRITERIA} non-empty strings"
        return [" ".join(c.split()) for c in raw]

    @staticmethod
    def _has_criteria_table(text: str, criteria: list[str]) -> bool:
        """Return True if synthesis text includes a Markdown table covering every criterion."""
        if not criteria:
            return True
        if not _MARKDOWN_TABLE_SEP_RE.search(text):
            return False
        lowered = text.lower()
        return all(c.lower() in lowered for c in criteria)

    @staticmethod
    def _pick_private_synthesizer(speaking: list[Debater], active: Any) -> str | None:
        """Choose an independent privacy-cleared synthesizer when active_model spoke or fails."""
        speaking_models = {d.model for d in speaking}
        if (
            isinstance(active, str)
            and active
            and not is_non_private_model(active)
            and active not in speaking_models
        ):
            return None
        for candidate in PRIVATE_SYNTHESIS_FALLBACKS:
            if candidate not in speaking_models:
                return candidate
        return speaking[0].model

    @staticmethod
    def _seat_debaters(
        parameters: dict[str, Any], *, private_only: bool = False
    ) -> list[Debater] | str:
        """The debaters for this request, or an error message."""
        topic = parameters.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return "Topic is required for a debate"

        positions = parameters.get("positions") or []
        default_panel = PRIVATE_DEFAULT_PANEL if private_only else DEFAULT_PANEL
        models = parameters.get("models") or default_panel
        if not isinstance(positions, list) or not all(
            isinstance(p, str) and p.strip() for p in positions
        ):
            return "positions must be a list of non-empty strings"
        if not isinstance(models, list) or not all(isinstance(m, str) and m for m in models):
            return "models must be a list of model IDs"

        for mid in models:
            if is_excluded_model(mid):
                return f"Model '{mid}' is excluded by policy"
            if private_only and is_non_private_model(mid):
                return f"Model '{mid}' is excluded when private_only=True"

        if positions and parameters.get("models") and len(models) > len(positions):
            return (
                f"{len(models)} models for {len(positions)} positions would leave models out: "
                "give at most one model per position (fewer models are reused in turn)"
            )

        count = len(positions) if positions else len(models)
        if not MIN_DEBATERS <= count <= MAX_DEBATERS:
            what = "positions" if positions else "models"
            return f"A debate needs {MIN_DEBATERS}-{MAX_DEBATERS} debaters; got {count} {what}"

        return [
            Debater(
                number=i + 1,
                model=models[i % len(models)],
                stance=" ".join(positions[i].split()) if positions else None,
            )
            for i in range(count)
        ]

    async def _run(
        self,
        model_manager: Any,
        topic: str,
        debaters: list[Debater],
        rounds: int,
        parameters: dict[str, Any],
        *,
        criteria: list[str] | None = None,
        private_only: bool = False,
        synthesis_model: str | None = None,
    ) -> ToolOutput:
        """Run the rounds and assemble the transcript."""
        del parameters
        crit_list = criteria or []
        calls = 0
        total = len(debaters) * rounds + 1
        sections = [f"🏛️ Debate: {topic}"]
        if crit_list:
            sections.append(f"**Criteria:** {', '.join(crit_list)}")

        async def call(label: str, prompt: str, model: str | None) -> Turn:
            """One model call, reported to the client as soon as it finishes."""
            nonlocal calls
            turn = await self._call(model_manager, prompt, model, private_only=private_only)
            calls += 1
            outcome = "in" if turn.text is not None else "failed"
            report_progress(calls, total, f"{label} {outcome}")
            return turn

        report_progress(0, total, f"Openings: {len(debaters)} debaters")

        openings = await asyncio.gather(
            *(
                call(
                    f"Opening from {d.title} ({d.model})",
                    self._opening_prompt(topic, d, crit_list),
                    d.model,
                )
                for d in debaters
            )
        )
        sections.append("## Round 1: Opening statements")
        for debater, turn in zip(debaters, openings, strict=True):
            debater.opening = turn.text
            sections.append(self._format_turn(debater, turn))

        speaking = [d for d in debaters if d.opening]
        if len(speaking) < MIN_DEBATERS:
            failures = "; ".join(
                f"{d.title} ({d.model}): {t.error}"
                for d, t in zip(debaters, openings, strict=True)
                if t.error
            )
            return ToolOutput(
                success=False,
                error=f"Too few debaters answered to hold a debate. {failures}",
            )

        total = calls + (len(speaking) if rounds == 2 else 0) + 1

        if rounds == 2:
            rebuttals = await asyncio.gather(
                *(
                    call(
                        f"Rebuttal from {d.title} ({d.model})",
                        self._rebuttal_prompt(topic, d, speaking, crit_list),
                        d.model,
                    )
                    for d in speaking
                )
            )
            sections.append("## Round 2: Rebuttals")
            for debater, turn in zip(speaking, rebuttals, strict=True):
                debater.rebuttal = turn.text
                sections.append(self._format_turn(debater, turn))

        effective_synth = synthesis_model
        if private_only and effective_synth is None:
            active = getattr(model_manager, "active_model", None)
            effective_synth = self._pick_private_synthesizer(speaking, active)

        synthesis = await call(
            "Synthesis",
            self._synthesis_prompt(topic, speaking, crit_list),
            effective_synth,
        )
        sections.append("## Synthesis")
        missing_criteria_table = False
        if synthesis.text is not None:
            synth_body = synthesis.text
            if crit_list and not self._has_criteria_table(synth_body, crit_list):
                missing_criteria_table = True
                synth_body += (
                    "\n\n⚠️ *Synthesis omitted a complete Markdown criteria table; "
                    "this response will not be cached.*"
                )
            shared_note = ""
            judge_model = effective_synth
            if judge_model is None:
                active_cand = getattr(model_manager, "active_model", None)
                if isinstance(active_cand, str):
                    judge_model = active_cand
            if judge_model and any(d.model == judge_model for d in speaking):
                shared_note = " *(participating model)*"
            sections.append(f"{synth_body}\n\n*[Model: {synthesis.model_used}]{shared_note}*")
        else:
            sections.append(f"⚠️ The synthesis failed: {synthesis.error}")

        missing_rebuttal = rounds == 2 and any(d.rebuttal is None for d in speaking)
        incomplete = (
            any(t.error for t in openings)
            or missing_rebuttal
            or bool(synthesis.error)
            or missing_criteria_table
        )
        sections.append(
            f"[Debate: {len(debaters)} debaters, {rounds} round{'s' if rounds > 1 else ''}, "
            f"{calls} calls]"
        )

        output = ToolOutput(success=True, result="\n\n".join(sections))
        if incomplete:
            output.metadata["cacheable"] = False
        return output

    @staticmethod
    async def _call(
        model_manager: Any,
        prompt: str,
        model: str | None,
        *,
        private_only: bool = False,
    ) -> Turn:
        """One model call on a worker thread, so the debaters' calls overlap."""
        try:
            call_kwargs: dict[str, Any] = {"model": model}
            if private_only:
                call_kwargs["private_only"] = True
            text, model_used = await asyncio.to_thread(
                model_manager.generate_content, prompt, **call_kwargs
            )
            if not text or not text.strip():
                return Turn(text=None, model_used=model_used, error="empty reply")
            return Turn(text=text, model_used=model_used)
        except Exception as e:
            logger.warning(f"Debate call to {model or 'the active model'} failed: {e}")
            return Turn(
                text=None, model_used=model or "active model", error=str(e)[:ERROR_PREVIEW_CHARS]
            )

    @staticmethod
    def _format_turn(debater: Debater, turn: Turn) -> str:
        """One debater's turn in the transcript."""
        if turn.text is None:
            return f"### {debater.title}\n\n⚠️ {debater.model} failed: {turn.error}"
        return f"### {debater.title}\n\n{turn.text}\n\n*[Model: {turn.model_used}]*"

    @staticmethod
    def _opening_prompt(topic: str, debater: Debater, criteria: list[str] | None = None) -> str:
        """The opening-statement prompt."""
        if debater.stance:
            task = (
                f"Argue for this position: {debater.stance}\n\n"
                "Make the strongest honest case for it: your main argument, the reasoning "
                "or evidence behind it, and the weaknesses you concede."
            )
        else:
            task = (
                "Give your own answer: your position, the reasoning behind it, and what "
                "would change your mind."
            )
        if criteria:
            bullets = "\n".join(f"- {c}" for c in criteria)
            task += f"\n\nEvaluate your position explicitly against these criteria:\n{bullets}"
        return (
            f"You are one of several AI models in a structured debate on:\n{topic}\n\n"
            f"{task}\n\nBe concise: under 300 words."
        )

    @staticmethod
    def _rebuttal_prompt(
        topic: str,
        debater: Debater,
        speaking: list[Debater],
        criteria: list[str] | None = None,
    ) -> str:
        """The rebuttal prompt: this debater's opening plus everyone else's."""
        others = "\n\n".join(
            f"**{other.title}:**\n{other.opening}"
            for other in speaking
            if other.number != debater.number
        )
        crit_note = ""
        if criteria:
            crit_note = (
                f" Address how the competing arguments hold up on the criteria "
                f"({', '.join(criteria)})."
            )
        return (
            f"You are {debater.title} in a structured debate on:\n{topic}\n\n"
            f"Your opening statement:\n{debater.opening}\n\n"
            f"The other debaters said:\n\n{others}\n\n"
            "Respond to them: where they are wrong, what they get right, and whether "
            f"anything they said changes your position.{crit_note} Be concise: under 200 words."
        )

    @staticmethod
    def _synthesis_prompt(
        topic: str, speaking: list[Debater], criteria: list[str] | None = None
    ) -> str:
        """The synthesis prompt, carrying the whole transcript."""
        transcript = []
        for debater in speaking:
            entry = f"**{debater.title} ({debater.model}), opening:**\n{debater.opening}"
            if debater.rebuttal:
                entry += f"\n\n**{debater.title}, rebuttal:**\n{debater.rebuttal}"
            transcript.append(entry)
        joined = "\n\n".join(transcript)
        if criteria:
            crit_bullets = "\n".join(f"- {c}" for c in criteria)
            return (
                f"You are judging a structured debate between AI models on:\n{topic}\n\n"
                f"Decision criteria:\n{crit_bullets}\n\n"
                f"{joined}\n\n"
                "Write a synthesis:\n"
                "1. Where the debaters agree\n"
                "2. The real disagreements, and which side argued each one better\n"
                "3. A Markdown Criteria Decision Table (`| Criterion | ... |`) naming every "
                "criterion above and scoring each position/option, plus concise Pros & Cons\n"
                "4. Arguments that didn't hold up\n"
                "5. Your recommendation grounded in the criteria, and how confident you are in it"
            )
        return (
            f"You are judging a structured debate between AI models on:\n{topic}\n\n"
            f"{joined}\n\n"
            "Write a synthesis:\n"
            "1. Where the debaters agree\n"
            "2. The real disagreements, and which side argued each one better\n"
            "3. Arguments that didn't hold up\n"
            "4. Your recommendation, and how confident you are in it"
        )
