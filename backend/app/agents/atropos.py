"""Atropos - The Terminator v2.0.

Three death triggers (no HP death):
1. Nemesis signals `lethal_punishment` (broken oath)
2. LLM check: given state + action, is this a narrative dead-end?
3. Keyword detection: "surrender to death", "embrace the void", etc.
4. Dead soul: all vectors collapsed to <= 1.0

Phase 1: Deterministic checks (keywords + dead soul).
Phase 2: LLM-evaluated narrative dead-ends via Mercury.
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import AtroposResponse, ThreadState
from app.services import llm
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.atropos")


# ---------------------------------------------------------------------------
# Death keyword triggers
# ---------------------------------------------------------------------------

_DEATH_TRIGGERS = [
    "surrender to death",
    "embrace the void",
    "drink the poison",
    "jump off",
    "end my thread",
    "cut my own thread",
    "give up completely",
    "welcome oblivion",
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Atropos(AgentBase):
    name = "atropos"

    async def evaluate(
        self, state: ThreadState, action: str,
        nemesis_lethal: bool = False,
    ) -> AtroposResponse:
        """Check for terminal conditions.

        Args:
            state: Current thread state.
            action: Player's action this turn.
            nemesis_lethal: True if Nemesis flagged lethal_punishment (oath broken).
        """
        # --- Trigger 1: Nemesis lethal punishment (broken oath) ---
        if nemesis_lethal:
            logger.info("Atropos: Thread severed — Oath broken, Nemesis demands death.")
            return AtroposResponse(
                terminal_state=True,
                death_reason=(
                    "You broke a sacred oath. The thread of your fate snaps — "
                    "Nemesis claims what was promised."
                ),
            )

        # --- Trigger 2: Dead soul (all vectors <= 1.0) ---
        if SoulVectorEngine.is_dead_soul(state.soul_ledger.vectors):
            logger.info("Atropos: Thread severed — Dead soul (all vectors collapsed).")
            return AtroposResponse(
                terminal_state=True,
                death_reason=(
                    "Your soul gutters like a candle in wind. Every dimension "
                    "of your being has faded to nothing. The thread dissolves."
                ),
            )

        # --- Trigger 3: Self-destruction keywords ---
        action_lower = action.lower()
        if any(trigger in action_lower for trigger in _DEATH_TRIGGERS):
            logger.info("Atropos: Thread severed — Self-destruction detected.")
            return AtroposResponse(
                terminal_state=True,
                death_reason="You chose oblivion. The thread ends by your own hand.",
            )

        # --- Trigger 4: LLM narrative dead-end check (Phase 2) ---
        # Only check if we have enough turns of context
        if state.session.turn_count >= 5 and state.rag_context:
            is_dead_end = await self._check_narrative_dead_end(state, action)
            if is_dead_end:
                logger.info("Atropos: Thread severed — Narrative dead-end.")
                return AtroposResponse(
                    terminal_state=True,
                    death_reason=(
                        "The story has nowhere left to go. Your thread frays "
                        "at the edges, unraveling into silence."
                    ),
                )

        # --- Warning state: vectors getting dangerously low ---
        vectors = state.soul_ledger.vectors
        vals = list(vectors.model_dump().values())
        if all(v <= 2.0 for v in vals):
            return AtroposResponse(
                terminal_state=False,
                death_reason="The Fates grow restless. Your soul dims.",
            )

        return AtroposResponse(terminal_state=False)

    async def _check_narrative_dead_end(
        self, state: ThreadState, action: str
    ) -> bool:
        """Use LLM to check if the narrative has reached a dead end.

        Only called after sufficient turns. Returns True if the story
        is irrecoverably stuck.
        """
        model = settings.nemesis_model  # Reuse Nemesis's model for this check

        if model == "mock":
            return False  # Mock mode never triggers narrative dead-end

        system = (
            "You are a narrative analyst. Given the game state and recent history, "
            "determine if the player's story has reached a GENUINE dead end — "
            "not just a difficult situation, but a truly irrecoverable state "
            "where no meaningful action is possible. Respond with ONLY 'true' or 'false'."
        )
        context = (
            f"Recent turns: {state.rag_context[-5:]}\n"
            f"Current environment: {state.session.current_environment}\n"
            f"Last action: {action}\n"
            f"Soul vectors: {state.soul_ledger.vectors.model_dump()}"
        )

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=system,
                user_message=context,
                temperature=0.1,
                max_tokens=10,
            )
            return raw.strip().lower() == "true"
        except Exception as e:
            logger.warning(f"Atropos dead-end check failed: {e}")
            return False
