"""Debate tool: several models argue a topic, rebut each other, and one synthesizes."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .base import MCPTool, ToolOutput

logger = logging.getLogger(__name__)

# Three families, so the debate isn't one model agreeing with itself.
# GLM runs on the flat-rate Z.ai plan when its key is set.
DEFAULT_PANEL = ["~openai/gpt-sol-latest", "~z-ai/glm-latest", "~moonshotai/kimi-latest"]
MIN_DEBATERS = 2
MAX_DEBATERS = 4
ERROR_PREVIEW_CHARS = 200


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
            "Default panel: GPT, GLM and Kimi. Makes one call per debater per round, plus one; "
            "each round waits for its slowest model, so a debate with reasoning models can "
            "take several minutes."
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
                        f"Default: {', '.join(DEFAULT_PANEL)}"
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
            },
            "required": ["topic"],
        }

    def is_cacheable(self, parameters: dict[str, Any]) -> bool:
        """The answer depends only on the input and the models."""
        return True

    async def execute(self, parameters: dict[str, Any]) -> ToolOutput:
        """Execute the tool."""
        try:
            debaters_or_error = self._seat_debaters(parameters)
            if isinstance(debaters_or_error, str):
                return ToolOutput(success=False, error=debaters_or_error)
            debaters = debaters_or_error

            topic = parameters["topic"].strip()
            rounds = parameters.get("rounds", 2)
            if isinstance(rounds, bool) or rounds not in (1, 2):
                return ToolOutput(success=False, error="rounds must be 1 or 2")

            # Get model manager from server instance
            try:
                from .. import _server_instance

                if _server_instance and _server_instance.model_manager:
                    model_manager = _server_instance.model_manager
                else:
                    raise AttributeError("Server instance not available")
            except (ImportError, AttributeError):
                # Fallback for bundled mode - model_manager should be global
                model_manager = globals().get("model_manager")
                if not model_manager:
                    return ToolOutput(success=False, error="Model manager not available")

            return await self._run(model_manager, topic, debaters, rounds, parameters)
        except Exception as e:
            logger.error(f"Debate error: {e}")
            return ToolOutput(success=False, error=f"Error: {str(e)}")

    @staticmethod
    def _seat_debaters(parameters: dict[str, Any]) -> list[Debater] | str:
        """The debaters for this request, or an error message."""
        topic = parameters.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return "Topic is required for a debate"

        positions = parameters.get("positions") or []
        models = parameters.get("models") or DEFAULT_PANEL
        if not isinstance(positions, list) or not all(
            isinstance(p, str) and p.strip() for p in positions
        ):
            return "positions must be a list of non-empty strings"
        if not isinstance(models, list) or not all(isinstance(m, str) and m for m in models):
            return "models must be a list of model IDs"

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
    ) -> ToolOutput:
        """Run the rounds and assemble the transcript."""
        calls = 0
        sections = [f"🏛️ Debate: {topic}"]

        # Round 1: every debater opens at once
        openings = await asyncio.gather(
            *(self._call(model_manager, self._opening_prompt(topic, d), d.model) for d in debaters)
        )
        calls += len(debaters)
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

        # Round 2: each debater answers all the others in one call
        if rounds == 2:
            rebuttals = await asyncio.gather(
                *(
                    self._call(model_manager, self._rebuttal_prompt(topic, d, speaking), d.model)
                    for d in speaking
                )
            )
            calls += len(speaking)
            sections.append("## Round 2: Rebuttals")
            for debater, turn in zip(speaking, rebuttals, strict=True):
                debater.rebuttal = turn.text
                sections.append(self._format_turn(debater, turn))

        synthesis = await self._call(
            model_manager,
            self._synthesis_prompt(topic, speaking),
            parameters.get("synthesis_model"),
        )
        calls += 1
        sections.append("## Synthesis")
        if synthesis.text is not None:
            sections.append(f"{synthesis.text}\n\n*[Model: {synthesis.model_used}]*")
        else:
            sections.append(f"⚠️ The synthesis failed: {synthesis.error}")

        missing_rebuttal = rounds == 2 and any(d.rebuttal is None for d in speaking)
        incomplete = any(t.error for t in openings) or missing_rebuttal or bool(synthesis.error)
        sections.append(
            f"[Debate: {len(debaters)} debaters, {rounds} round{'s' if rounds > 1 else ''}, "
            f"{calls} calls]"
        )

        output = ToolOutput(success=True, result="\n\n".join(sections))
        if incomplete:
            # Don't serve a debate with a missing voice from cache for the next hour
            output.metadata["cacheable"] = False
        return output

    @staticmethod
    async def _call(model_manager: Any, prompt: str, model: str | None) -> Turn:
        """One model call on a worker thread, so the debaters' calls overlap."""
        try:
            text, model_used = await asyncio.to_thread(
                model_manager.generate_content, prompt, model=model
            )
            if not text or not text.strip():
                # Providers turn a missing reply into "": that's a failed turn, not a speech
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
    def _opening_prompt(topic: str, debater: Debater) -> str:
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
        return (
            f"You are one of several AI models in a structured debate on:\n{topic}\n\n"
            f"{task}\n\nBe concise: under 300 words."
        )

    @staticmethod
    def _rebuttal_prompt(topic: str, debater: Debater, speaking: list[Debater]) -> str:
        """The rebuttal prompt: this debater's opening plus everyone else's."""
        others = "\n\n".join(
            f"**{other.title}:**\n{other.opening}"
            for other in speaking
            if other.number != debater.number
        )
        return (
            f"You are {debater.title} in a structured debate on:\n{topic}\n\n"
            f"Your opening statement:\n{debater.opening}\n\n"
            f"The other debaters said:\n\n{others}\n\n"
            "Respond to them: where they are wrong, what they get right, and whether "
            "anything they said changes your position. Be concise: under 200 words."
        )

    @staticmethod
    def _synthesis_prompt(topic: str, speaking: list[Debater]) -> str:
        """The synthesis prompt, carrying the whole transcript."""
        transcript = []
        for debater in speaking:
            entry = f"**{debater.title} ({debater.model}), opening:**\n{debater.opening}"
            if debater.rebuttal:
                entry += f"\n\n**{debater.title}, rebuttal:**\n{debater.rebuttal}"
            transcript.append(entry)
        joined = "\n\n".join(transcript)
        return (
            f"You are judging a structured debate between AI models on:\n{topic}\n\n"
            f"{joined}\n\n"
            "Write a synthesis:\n"
            "1. Where the debaters agree\n"
            "2. The real disagreements, and which side argued each one better\n"
            "3. Arguments that didn't hold up\n"
            "4. Your recommendation, and how confident you are in it"
        )
