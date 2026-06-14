"""Atropos - The Terminator v3.0 (Staged Doom).

Death triggers:
1. Doom terminal: an active doom (broken oath, mortal wounds, manhunt,
   lethal clock) has reached its final stage. Dooms are begun by the
   kernel and advance one stage per turn — death arrives in installments,
   never as an instant sever.
2. Dead soul: all vectors collapsed to <= 1.0
3. Keyword detection: "surrender to death", "embrace the void", etc.
4. LLM check: given state + action, is this a narrative dead-end?

A broken oath no longer kills on the turn it breaks; it seals a doom
(see services/doom.py). Atropos only cuts when the doom matures.
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import AgentProposal, AtroposResponse, ThreadState
from app.services import llm
from app.services.doom import doom_death_reason, is_doom_terminal
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.atropos")


def _attach_proposal(
    response: AtroposResponse,
    *,
    action: str,
    nemesis_lethal: bool,
) -> AtroposResponse:
    """Attach a structured proposal to an Atropos response."""
    scene_patch: dict[str, object] = {}
    if response.death_reason:
        scene_patch["warning"] = response.death_reason
    if nemesis_lethal:
        scene_patch["trigger"] = "broken_oath"

    response.proposal = AgentProposal(
        agent="atropos",
        allow_action=True,
        scene_patch=scene_patch,
        death_flag=response.terminal_state,
        death_reason=response.death_reason if response.terminal_state else "",
        intervention_copy=response.death_reason,
        priority_note="Finality and irreversible consequence.",
        confidence=1.0 if response.terminal_state else 0.8,
    )
    return response


# Death triggers loaded from settings (configurable via .env)
# Fallback list is defined in config.py


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
            nemesis_lethal: True if Nemesis flagged lethal_punishment this
                turn (oath broken). No longer an instant death — the kernel
                seals a doom; Atropos cuts when that doom matures. The flag
                is kept for the proposal trace.
        """
        # --- Trigger 1: Doom terminal (staged death has matured) ---
        if is_doom_terminal(state):
            logger.info(
                f"Atropos: Thread severed — doom '{state.doom.cause}' "
                f"reached stage {state.doom.stage}/{state.doom.max_stage}."
            )
            return _attach_proposal(AtroposResponse(
                terminal_state=True,
                death_reason=doom_death_reason(state),
            ), action=action, nemesis_lethal=nemesis_lethal)

        # --- Trigger 2: Dead soul (all vectors <= 1.0) ---
        if SoulVectorEngine.is_dead_soul(state.soul_ledger.vectors):
            logger.info("Atropos: Thread severed — Dead soul (all vectors collapsed).")
            return _attach_proposal(AtroposResponse(
                terminal_state=True,
                death_reason=(
                    "Your soul gutters like a candle in wind. Every dimension "
                    "of your being has faded to nothing. The thread dissolves."
                ),
            ), action=action, nemesis_lethal=nemesis_lethal)

        # --- Trigger 3: Self-destruction keywords ---
        action_lower = action.lower()
        if any(trigger in action_lower for trigger in settings.atropos_death_keywords):
            logger.info("Atropos: Thread severed — Self-destruction detected.")
            return _attach_proposal(AtroposResponse(
                terminal_state=True,
                death_reason="You chose oblivion. The thread ends by your own hand.",
                self_destruction_origin=True,   # The Vigil: non-miracleable (permanence)
            ), action=action, nemesis_lethal=nemesis_lethal)

        # --- Trigger 4: LLM narrative dead-end check (Phase 2) ---
        # Only check if we have enough turns of context
        if state.session.turn_count >= 5 and state.rag_context:
            is_dead_end = await self._check_narrative_dead_end(state, action)
            if is_dead_end:
                logger.info("Atropos: Thread severed — Narrative dead-end.")
                return _attach_proposal(AtroposResponse(
                    terminal_state=True,
                    death_reason=(
                        "The story has nowhere left to go. Your thread frays "
                        "at the edges, unraveling into silence."
                    ),
                ), action=action, nemesis_lethal=nemesis_lethal)

        # --- Warning state: vectors getting dangerously low ---
        vectors = state.soul_ledger.vectors
        vals = list(vectors.model_dump().values())
        if all(v <= 2.0 for v in vals):
            return _attach_proposal(AtroposResponse(
                terminal_state=False,
                death_reason="The Fates grow restless. Your soul dims.",
            ), action=action, nemesis_lethal=nemesis_lethal)

        return _attach_proposal(
            AtroposResponse(terminal_state=False),
            action=action,
            nemesis_lethal=nemesis_lethal,
        )

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
