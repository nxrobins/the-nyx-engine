"""Hypnos - The Latency Mask / UI Streamer v2.0.

Streams atmospheric filler text instantly while the backend consensus
resolves. Must end in an ellipsis and NEVER resolve the action.

Phase 1: Pre-baked filler text.
Phase 2: Blazing-fast edge model (Haiku) for contextual fragments.

v2.0 changes:
- Payload uses environment + soul state instead of HP/hubris
- Model string via settings.hypnos_model (LiteLLM format)
- No more separate provider field
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import HypnosResponse, ThreadState
from app.services import llm
from app.services.prompt_loader import load_prompt

logger = logging.getLogger("nyx.hypnos")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/hypnos.yaml)
# ---------------------------------------------------------------------------

HYPNOS_SYSTEM_PROMPT = load_prompt("hypnos")


# ---------------------------------------------------------------------------
# Pre-baked fallback fragments (Phase 1)
# ---------------------------------------------------------------------------

_FILLER_FRAGMENTS = [
    "The air grows thick as you steel yourself...",
    "A tremor runs through the ground beneath your feet...",
    "Somewhere in the distance, something stirs...",
    "Your pulse quickens. The moment stretches like pulled thread...",
    "The weight of your choice presses against reality itself...",
    "Shadows bend and whisper in a language older than words...",
    "Time holds its breath. The universe calculates...",
    "You feel the gaze of something ancient upon you...",
    "The Fates lean forward in their eternal seats...",
    "A cold wind carries the scent of consequence...",
    "The silence thickens around you like smoke...",
    "Your skin prickles with the electricity of the unseen...",
    "The world narrows to a single held breath...",
    "Something behind your ribs tightens with recognition...",
    "The stones beneath you hum with a frequency below hearing...",
]


def _mock_fragments() -> list[str]:
    """Pick 3 random fallback fragments."""
    return random.sample(_FILLER_FRAGMENTS, k=3)


def _parse_fragments(raw: str) -> list[str]:
    """Parse LLM output into a list of 3 fragments."""
    lines = [line.strip() for line in raw.strip().split("\n") if line.strip()]
    # Filter out any that look like metadata or are too short
    fragments = [
        line for line in lines
        if len(line) > 10 and not line.startswith(("{", "[", "#"))
    ]
    # Strip any numbering prefixes like "1. " or "- "
    cleaned = []
    for f in fragments[:3]:
        f = f.lstrip("0123456789.-) ").strip()
        # Ensure ellipsis ending
        if not f.endswith("..."):
            if f.endswith("."):
                f = f[:-1] + "..."
            else:
                f += "..."
        cleaned.append(f)
    return cleaned if cleaned else _mock_fragments()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Hypnos(AgentBase):
    name = "hypnos"

    async def evaluate(
        self, state: ThreadState, action: str
    ) -> HypnosResponse:
        """Generate filler text (non-streaming, used for SSE fallback)."""
        model = settings.hypnos_model
        if model == "mock":
            fragments = _mock_fragments()
        else:
            fragments = await self._generate_fragments(state, action)
        return HypnosResponse(filler_text="\n\n".join(fragments))

    async def stream_fragments(
        self, state: ThreadState, action: str
    ):
        """Async generator for SSE streaming of filler fragments.

        For LLM providers: generates all 3 fragments at once then streams
        them with pacing. Haiku is fast enough that this works perfectly.
        For mock: uses pre-baked fragments.
        """
        model = settings.hypnos_model

        if model == "mock":
            fragments = _mock_fragments()
        else:
            try:
                fragments = await self._generate_fragments(state, action)
            except Exception as e:
                logger.warning(f"Hypnos LLM failed: {e}. Using fallback.")
                fragments = _mock_fragments()

        for fragment in fragments:
            yield fragment
            await asyncio.sleep(settings.hypnos_fragment_delay)

    async def _generate_fragments(
        self, state: ThreadState, action: str
    ) -> list[str]:
        """Call the LLM for contextual filler fragments."""
        model = settings.hypnos_model

        # Ultra-concise prompt for speed — action + environment + vibe
        context = f"The mortal attempts: {action[:60]}"
        context += f"\nEnvironment: {state.session.current_environment[:80]}"

        # Soul state hints for atmospheric color
        vectors = state.soul_ledger.vectors
        vals = list(vectors.model_dump().values())
        if all(v <= 2.0 for v in vals):
            context += "\nTheir soul is nearly extinguished."
        elif max(vals) >= 8.0:
            context += "\nSomething vast stirs within them."

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=HYPNOS_SYSTEM_PROMPT,
                user_message=context,
                temperature=0.95,   # Maximum variety
                max_tokens=120,     # Ultra-short for speed
            )
            fragments = _parse_fragments(raw)
            logger.debug(f"Hypnos generated {len(fragments)} fragments")
            return fragments
        except Exception as e:
            logger.warning(f"Hypnos LLM error: {e}")
            return _mock_fragments()
