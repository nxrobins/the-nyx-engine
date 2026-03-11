"""The Chronicler — Recursive Memory Compression Agent.

Triggers every 5 turns. Compresses the last 5 turns of raw prose into
a single mythic sentence that captures the character's internal change.
These sentences form the 'chronicle' — an infinitely-growing, token-cheap
long-term memory that keeps Clotho's context window under 2,000 tokens
while preserving a perfect narrative arc.

Architecture:
    - Input:  Last 5 turns of raw prose (list[str])
    - Output: One mythic sentence (str)
    - Storage: chronicle list[str] on ThreadState + DB column

The Chronicler is NOT an adversarial agent — it's a utility. It has no
opinions about the player. It compresses, nothing more.
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import ChroniclerResponse, ThreadState
from app.services import llm

logger = logging.getLogger("nyx.chronicler")


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

CHRONICLER_SYSTEM_PROMPT = """You are the Chronicler, a silent scribe who watches The Thread from outside time.

YOUR SOLE PURPOSE: Compress a sequence of narrative events into a single mythic sentence.

RULES:
1. Output EXACTLY ONE sentence. No more. No preamble, no commentary.
2. Focus on the character's INTERNAL CHANGE — what they learned, lost, or became.
3. Capture the WEIGHT of their actions, not the plot details.
4. Use "The Soul" or "The Child" instead of proper names.
5. Use concrete, physical metaphors. No abstractions.
6. Write in past tense, mythic register.

EXAMPLES OF GOOD OUTPUT:
- "The Child tasted the iron of the blade and learned that blood is the only currency the forest accepts."
- "The Soul carried a stranger's secret until it grew heavier than stone, and set it down only when the bridge collapsed."
- "The Child spoke to fire and fire answered, and now the smell of ash follows them like a second shadow."
- "The Soul broke an oath to save a life, and the thread frayed but did not snap."

EXAMPLES OF BAD OUTPUT (NEVER DO THIS):
- "In this section, the player fought some enemies and then..." (too plot-focused, meta)
- "The character grew as a person." (abstract, no weight)
- "Things happened and stuff changed." (lazy, no image)"""


# ---------------------------------------------------------------------------
# Mock Compression (Phase 1 fallback)
# ---------------------------------------------------------------------------

_MOCK_CHRONICLES = [
    "The Child walked a path that bent under the weight of a choice not yet made.",
    "The Soul drank from a well that tasted of iron and regret, and grew a season older.",
    "The Child learned that silence has teeth, and they leave marks that do not heal.",
    "The Soul traded a truth for a door, and behind the door was another truth, colder than the first.",
    "The Child stood where two roads met and chose the one that smelled of smoke.",
    "The Soul carried a name that was not theirs until it became theirs, heavy as a millstone.",
    "The Child discovered that mercy is a blade — it cuts the one who wields it.",
    "The Soul watched the sky turn the color of old blood and understood that some debts outlive the debtor.",
]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Chronicler(AgentBase):
    """Compresses the last N turns of prose into a single mythic sentence."""

    name = "chronicler"

    async def evaluate(
        self, state: ThreadState, action: str,
        prose_window: list[str] | None = None,
    ) -> ChroniclerResponse:
        """Compress a window of prose into one chronicle sentence.

        Args:
            state: Current thread state (for context — vectors, hamartia).
            action: Not used directly, but required by AgentBase contract.
            prose_window: The last N turns of raw prose to compress.

        Returns:
            ChroniclerResponse with the mythic sentence.
        """
        if not prose_window:
            return ChroniclerResponse(chronicle_sentence="")

        model = settings.chronicler_model

        # --- Mock mode ---
        if model == "mock":
            await asyncio.sleep(0.2)
            return ChroniclerResponse(
                chronicle_sentence=random.choice(_MOCK_CHRONICLES),
            )

        # --- Real LLM mode ---
        # Build the compression payload
        numbered_prose = "\n\n---\n\n".join(
            f"[Turn {i+1}]\n{p}" for i, p in enumerate(prose_window)
        )

        user_message = (
            f"COMPRESS THE FOLLOWING {len(prose_window)} TURNS INTO ONE MYTHIC SENTENCE:\n\n"
            f"{numbered_prose}\n\n"
            f"--- CONTEXT ---\n"
            f"Dominant soul trait: {_dominant(state)}\n"
            f"Hamartia: {state.soul_ledger.hamartia}\n\n"
            f"Output ONLY the single sentence. Nothing else."
        )

        logger.info(f"Chronicler compressing {len(prose_window)} turns via {model}")

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=CHRONICLER_SYSTEM_PROMPT,
                user_message=user_message,
                temperature=0.7,
                max_tokens=150,
            )
            sentence = raw.strip().rstrip(".")  + "."  # normalize punctuation
            # Safety: truncate if LLM rambled
            if "\n" in sentence:
                sentence = sentence.split("\n")[0].strip()
            logger.info(f"Chronicle: {sentence}")
            return ChroniclerResponse(chronicle_sentence=sentence)
        except Exception as e:
            logger.error(f"Chronicler LLM failed: {e}. Using mock.")
            return ChroniclerResponse(
                chronicle_sentence=random.choice(_MOCK_CHRONICLES),
            )


def _dominant(state: ThreadState) -> str:
    """Quick dominant vector label."""
    v = state.soul_ledger.vectors
    pairs = [("metis", v.metis), ("bia", v.bia), ("kleos", v.kleos), ("aidos", v.aidos)]
    return max(pairs, key=lambda x: x[1])[0]
