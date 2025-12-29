"""Integration tests for the debate protocol."""

from unittest.mock import AsyncMock, Mock

import pytest

from council.core.orchestrator import ConversationOrchestrator
from council.models.base import ToolOutput
from council.protocols.debate import DebatePosition, DebateProtocol, DebateRound


class TestDebateProtocol:
    """Test suite for DebateProtocol."""

    @pytest.fixture
    def setup_debate(self):
        """Set up debate protocol with mocked orchestrator."""
        # Create mock orchestrator
        orchestrator = Mock(spec=ConversationOrchestrator)

        # Mock execute_tool to return successful responses
        async def mock_execute_tool(tool_name, parameters, **kwargs):
            if tool_name == "ask_gemini":
                # Return different responses based on the prompt content
                prompt = parameters.get("question", "")
                if "assigned position is: Pro" in prompt:
                    result_text = "Pro argument: This is beneficial because..."
                elif "assigned position is: Con" in prompt:
                    result_text = "Con argument: This could be harmful because..."
                else:
                    result_text = "Generic response"

                return ToolOutput(tool_name=tool_name, result=result_text, success=True)
            elif tool_name == "synthesize_perspectives":
                return ToolOutput(
                    tool_name=tool_name,
                    result="Synthesis: Both sides have valid points...",
                    success=True,
                )

            return ToolOutput(tool_name=tool_name, result="Mock result", success=True)

        orchestrator.execute_tool = AsyncMock(side_effect=mock_execute_tool)

        # Create debate
        topic = "Should AI be regulated?"
        positions = ["Pro regulation", "Against regulation"]
        debate = DebateProtocol(orchestrator, topic, positions)

        return debate, orchestrator

    @pytest.mark.asyncio
    async def test_debate_initialization(self, setup_debate):
        """Test debate protocol initialization."""
        debate, orchestrator = setup_debate

        assert debate.topic == "Should AI be regulated?"
        assert debate.positions == ["Pro regulation", "Against regulation"]
        assert debate.max_rounds == 3
        assert len(debate.rounds) == 0

    @pytest.mark.asyncio
    async def test_opening_statements(self, setup_debate):
        """Test generation of opening statements."""
        debate, orchestrator = setup_debate

        round1 = await debate._opening_statements()

        assert round1.round_number == 1
        assert len(round1.positions) == 2

        # Check positions
        pos1 = round1.positions[0]
        assert pos1.agent_name == "Agent_1"
        assert pos1.stance == "Pro regulation"
        assert len(pos1.arguments) > 0

        pos2 = round1.positions[1]
        assert pos2.agent_name == "Agent_2"
        assert pos2.stance == "Against regulation"

        # Verify orchestrator was called
        assert orchestrator.execute_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_rebuttal_round(self, setup_debate):
        """Test rebuttal round generation."""
        debate, orchestrator = setup_debate

        # First need opening statements
        round1 = await debate._opening_statements()
        debate.rounds.append(round1)

        # Reset call count
        orchestrator.execute_tool.reset_mock()

        # Generate rebuttals
        round2 = await debate._rebuttal_round()

        assert round2.round_number == 2
        assert len(round2.positions) == 2

        # Each position should have rebuttals against the other
        for position in round2.positions:
            assert len(position.rebuttals) == 1  # One rebuttal against the other position

        # Should have called execute_tool for each rebuttal
        assert orchestrator.execute_tool.call_count == 2  # 2 agents rebutting each other

    @pytest.mark.asyncio
    async def test_synthesis_round(self, setup_debate):
        """Test synthesis round."""
        debate, orchestrator = setup_debate

        # Set up previous rounds
        debate.rounds = [
            DebateRound(
                round_number=1,
                positions=[
                    DebatePosition("Agent_1", "Pro", ["Pro argument"]),
                    DebatePosition("Agent_2", "Con", ["Con argument"]),
                ],
            )
        ]

        synthesis = await debate._synthesis_round()

        assert "Synthesis: Both sides have valid points..." in synthesis

        # Check that synthesize_perspectives was called
        orchestrator.execute_tool.assert_called_with(
            "synthesize_perspectives",
            {
                "topic": "Should AI be regulated?",
                "perspectives": [
                    {"source": "Agent_1 (Pro)", "content": "Pro argument"},
                    {"source": "Agent_2 (Con)", "content": "Con argument"},
                ],
            },
        )

    @pytest.mark.asyncio
    async def test_full_debate_run(self, setup_debate):
        """Test running a full debate."""
        debate, orchestrator = setup_debate

        result = await debate.run()

        assert result["topic"] == "Should AI be regulated?"
        assert len(result["rounds"]) == 2  # Opening + Rebuttal
        assert "final_synthesis" in result
        assert result["positions_explored"] == 2

        # Verify all phases were executed
        # 2 opening statements + 2 rebuttals + 1 synthesis = 5 calls
        assert orchestrator.execute_tool.call_count == 5

    @pytest.mark.asyncio
    async def test_debate_with_failed_tool_execution(self, setup_debate):
        """Test debate handling when a tool execution fails."""
        debate, orchestrator = setup_debate

        # Make one execution fail
        fail_count = 0

        async def mock_execute_with_failure(tool_name, parameters, **kwargs):
            nonlocal fail_count
            if fail_count == 0 and tool_name == "ask_gemini":
                fail_count += 1
                return ToolOutput(
                    tool_name=tool_name, result=None, success=False, error="Mock failure"
                )
            # Default successful response
            return ToolOutput(tool_name=tool_name, result="Mock success", success=True)

        orchestrator.execute_tool = AsyncMock(side_effect=mock_execute_with_failure)

        # Run debate - should handle the failure gracefully
        round1 = await debate._opening_statements()

        # Should still complete, but one position might have empty arguments
        assert round1.round_number == 1
        assert len(round1.positions) <= 2  # Might have fewer if one failed

    @pytest.mark.asyncio
    async def test_rebuttal_without_opening_statements(self, setup_debate):
        """Test that rebuttal fails without opening statements."""
        debate, orchestrator = setup_debate

        # Try to generate rebuttals without opening statements
        with pytest.raises(ValueError, match="No opening statements to rebut"):
            await debate._rebuttal_round()

    def test_debate_position_dataclass(self):
        """Test DebatePosition dataclass."""
        position = DebatePosition(
            agent_name="TestAgent",
            stance="Pro",
            arguments=["Argument 1", "Argument 2"],
            confidence=0.8,
        )

        assert position.agent_name == "TestAgent"
        assert position.stance == "Pro"
        assert len(position.arguments) == 2
        assert position.confidence == 0.8
        assert len(position.rebuttals) == 0  # Default empty dict
