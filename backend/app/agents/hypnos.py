"""Hypnos — The Dream Weaver v3.0.

Generates surreal dream interludes at epoch boundaries (Resolution beats).
Dreams fire after turns 3, 6, 9 — bridging the years between childhood phases.
The dream text is stored on state.current_dream and consumed by the next
Clotho call via the stratified context's Dream Bleed section.

v3.0 changes (Sprint 8: Hypnos Reborn):
- Full rewrite: latency mask → dream weaver
- evaluate() / stream_fragments() deleted
- New weave_dream() generates 2-3 sentences of surreal imagery
- Mock dreams pool for Phase 1 testing
- Soul vector coloring via dominant_vector()
"""

from __future__ import annotations

import logging
import random

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import HypnosResponse, ThreadState
from app.services import llm
from app.services.prompt_loader import load_prompt
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.hypnos")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/hypnos.yaml)
# ---------------------------------------------------------------------------

HYPNOS_DREAM_PROMPT = load_prompt("hypnos")


# ---------------------------------------------------------------------------
# Mock Dreams (Phase 1 fallback)
# ---------------------------------------------------------------------------

_MOCK_DREAMS: list[str] = [
    "You are running through a field of golden wheat that reaches above your "
    "head. Each stalk whispers a name you almost recognize. The sky is the "
    "wrong colour.",

    "Your mother's voice calls from behind a door that keeps moving further "
    "away. Your feet leave no prints on the glass floor. Something warm drips "
    "from the ceiling.",

    "You are sitting in a classroom where all the other children have your "
    "face. The teacher writes an equation on the board: your name = something "
    "you can't read.",

    "A river flows uphill through your bedroom. Fish with human eyes swim "
    "past your pillow. One of them mouths a word that tastes like copper.",

    "You climb a tree that grows through every room of a house you've never "
    "seen. At the top, a bird made of newspaper sings tomorrow's weather. "
    "You believe every word.",

    "The hallway stretches forever in both directions. Every door opens onto "
    "the same room: yours, but older. In the last one, someone has left a "
    "candle burning.",
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Hypnos(AgentBase):
    name = "hypnos"

    async def evaluate(self, state: ThreadState, action: str) -> HypnosResponse:
        """ABC contract stub — Hypnos no longer uses the standard evaluate path.

        The kernel calls weave_dream() directly at epoch boundaries.
        This exists only to satisfy the AgentBase abstract method.
        """
        dream = await self.weave_dream(state)
        return HypnosResponse(filler_text=dream)

    async def weave_dream(self, state: ThreadState) -> str:
        """Generate a dream interlude for an epoch boundary.

        Returns 2-3 sentences of surreal, age-appropriate dream imagery.
        Uses dominant soul vector to color the dream's emotional tone.
        """
        model = settings.hypnos_model

        if model == "mock":
            return random.choice(_MOCK_DREAMS)

        dominant = SoulVectorEngine.dominant_vector(state.soul_ledger.vectors)
        age = state.session.player_age

        user_msg = (
            f"Age: {age}\n"
            f"Dominant soul vector: {dominant}\n"
            f"Hamartia: {state.soul_ledger.hamartia}\n"
            f"Environment: {state.session.current_environment}\n"
            f"Last action: {state.last_action}"
        )

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=HYPNOS_DREAM_PROMPT,
                user_message=user_msg,
                temperature=0.95,
                max_tokens=200,
            )
            dream = raw.strip()
            if len(dream) < 20:
                logger.warning("Hypnos dream too short, using fallback")
                return random.choice(_MOCK_DREAMS)
            return dream
        except Exception as e:
            logger.warning(f"Hypnos dream LLM failed: {e}")
            return random.choice(_MOCK_DREAMS)
