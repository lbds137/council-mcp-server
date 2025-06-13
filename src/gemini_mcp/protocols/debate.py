"""Debate protocol for structured multi-agent discussions."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ..models.base import ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class DebatePosition:
    """Represents a position in a debate."""
    agent_name: str
    stance: str
    arguments: List[str] = field(default_factory=list)
    rebuttals: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class DebateRound:
    """Represents a round of debate."""
    round_number: int
    positions: List[DebatePosition]
    synthesis: Optional[str] = None


class DebateProtocol:
    """Orchestrates structured debates between multiple agents."""
    
    def __init__(self, orchestrator, topic: str, positions: List[str]):
        self.orchestrator = orchestrator
        self.topic = topic
        self.positions = positions
        self.rounds: List[DebateRound] = []
        self.max_rounds = 3
    
    async def run(self) -> Dict[str, Any]:
        """Run the debate protocol."""
        logger.info(f"Starting debate on topic: {self.topic}")
        
        # Round 1: Opening statements
        round1 = await self._opening_statements()
        self.rounds.append(round1)
        
        # Round 2: Rebuttals
        round2 = await self._rebuttal_round()
        self.rounds.append(round2)
        
        # Round 3: Final synthesis
        synthesis = await self._synthesis_round()
        
        return {
            "topic": self.topic,
            "rounds": self.rounds,
            "final_synthesis": synthesis,
            "positions_explored": len(self.positions)
        }
    
    async def _opening_statements(self) -> DebateRound:
        """Generate opening statements for each position."""
        logger.info("Debate Round 1: Opening statements")
        
        debate_positions = []
        
        for i, position in enumerate(self.positions):
            # Create a persona for this position
            prompt = f"""You are participating in a structured debate on the topic: {self.topic}
            
Your assigned position is: {position}

Please provide:
1. Your main argument (2-3 sentences)
2. Three supporting points
3. Your confidence level (0.0-1.0) in this position
4. Any caveats or limitations you acknowledge

Be concise but persuasive."""
            
            # Execute via orchestrator
            result = await self.orchestrator.execute_tool(
                "ask_gemini",
                {"question": prompt, "context": f"Debate agent {i+1}"}
            )
            
            if result.success:
                # Parse the response (in a real implementation, we'd use structured output)
                debate_position = DebatePosition(
                    agent_name=f"Agent_{i+1}",
                    stance=position,
                    arguments=[result.result],  # Simplified for now
                    confidence=0.7  # Would be parsed from response
                )
                debate_positions.append(debate_position)
        
        return DebateRound(
            round_number=1,
            positions=debate_positions
        )
    
    async def _rebuttal_round(self) -> DebateRound:
        """Generate rebuttals for each position."""
        logger.info("Debate Round 2: Rebuttals")
        
        if not self.rounds:
            raise ValueError("No opening statements to rebut")
        
        previous_positions = self.rounds[0].positions
        updated_positions = []
        
        for i, position in enumerate(previous_positions):
            rebuttals = {}
            
            # Generate rebuttals against other positions
            for j, other_position in enumerate(previous_positions):
                if i == j:
                    continue
                
                prompt = f"""You previously argued for: {position.stance}

The opposing view argues: {other_position.arguments[0]}

Please provide:
1. A concise rebuttal to their argument
2. Why your position is stronger
3. Any points of agreement or common ground

Keep your response under 100 words."""
                
                result = await self.orchestrator.execute_tool(
                    "ask_gemini",
                    {"question": prompt, "context": f"Rebuttal from {position.agent_name}"}
                )
                
                if result.success:
                    rebuttals[other_position.agent_name] = result.result
            
            # Update position with rebuttals
            position.rebuttals = rebuttals
            updated_positions.append(position)
        
        return DebateRound(
            round_number=2,
            positions=updated_positions
        )
    
    async def _synthesis_round(self) -> str:
        """Synthesize all positions into a final analysis."""
        logger.info("Debate Round 3: Synthesis")
        
        # Prepare perspectives for synthesis tool
        perspectives = []
        
        for round in self.rounds:
            for position in round.positions:
                perspectives.append({
                    "source": f"{position.agent_name} ({position.stance})",
                    "content": " ".join(position.arguments)
                })
        
        # Use the synthesize_perspectives tool
        result = await self.orchestrator.execute_tool(
            "synthesize_perspectives",
            {
                "topic": self.topic,
                "perspectives": perspectives
            }
        )
        
        return result.result if result.success else "Failed to synthesize debate"