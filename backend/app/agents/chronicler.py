"""The Chronicler — Dual-Track Memory Compression Agent v2.0.

Triggers every 5 turns. Produces two parallel compression tracks:

1. **Mythic Track** (LLM-powered) — one poetic sentence capturing the
   character's internal change. Used by Clotho for narrative tone.

2. **Factual Track** (deterministic) — structured state snapshot capturing
   environment, vectors, oaths, prophecy. Used by Lachesis/Momus for
   consistency checking. Zero LLM tokens.

Together, these form an infinitely-growing, token-cheap long-term memory
that keeps Clotho's context window under 2,000 tokens while preserving
both narrative arc AND factual state history.

Architecture:
    - Input:  Last 5 turns of raw prose (list[str]) + ThreadState
    - Output: ChroniclerResponse(chronicle_sentence, factual_digest)
    - Storage: chronicle + factual_chronicle on ThreadState + DB columns

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
from app.services.prompt_loader import load_prompt

logger = logging.getLogger("nyx.chronicler")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/chronicler.yaml)
# ---------------------------------------------------------------------------

CHRONICLER_SYSTEM_PROMPT = load_prompt("chronicler")


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
# Factual Digest Builder (deterministic — no LLM needed)
# ---------------------------------------------------------------------------

def _build_factual_digest(state: ThreadState, prose_window: list[str]) -> str:
    """Build a deterministic factual state snapshot.

    Captures concrete facts for consistency checking:
    environment, dominant vector, hamartia, active oaths, prophecy.
    This costs zero LLM tokens — pure string assembly from state.
    """
    parts: list[str] = []

    # Environment
    env = state.session.current_environment
    if env:
        # Truncate long environments to keep digests compact
        parts.append(f"Setting: {env[:80]}")

    # Soul vectors — dominant + all values
    dom = _dominant(state)
    v = state.soul_ledger.vectors
    dom_val = getattr(v, dom)
    parts.append(f"Dominant: {dom} ({dom_val:.1f})")

    # Hamartia
    if state.soul_ledger.hamartia:
        parts.append(f"Flaw: {state.soul_ledger.hamartia}")

    # Active oaths (truncated)
    if state.soul_ledger.active_oaths:
        oath_texts = [o.text[:50] for o in state.soul_ledger.active_oaths[:3]]
        parts.append(f"Oaths: {'; '.join(oath_texts)}")

    # Prophecy
    if state.the_loom.current_prophecy:
        parts.append(f"Prophecy: {state.the_loom.current_prophecy[:80]}")

    # Epoch
    parts.append(f"Epoch: {state.session.epoch_phase}")

    # Window size
    parts.append(f"Turns compressed: {len(prose_window)}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Chronicler(AgentBase):
    """Dual-track memory compression: mythic (LLM) + factual (deterministic)."""

    name = "chronicler"

    async def evaluate(
        self, state: ThreadState, action: str,
        prose_window: list[str] | None = None,
    ) -> ChroniclerResponse:
        """Compress a window of prose into dual-track output.

        Args:
            state: Current thread state (for context — vectors, hamartia).
            action: Not used directly, but required by AgentBase contract.
            prose_window: The last N turns of raw prose to compress.

        Returns:
            ChroniclerResponse with both mythic sentence and factual digest.
        """
        if not prose_window:
            return ChroniclerResponse(chronicle_sentence="", factual_digest="")

        # --- Factual track (always deterministic, zero tokens) ---
        factual = _build_factual_digest(state, prose_window)

        # --- Mythic track ---
        mythic = await self._compress_mythic(state, prose_window)

        return ChroniclerResponse(
            chronicle_sentence=mythic,
            factual_digest=factual,
        )

    async def _compress_mythic(
        self, state: ThreadState, prose_window: list[str],
    ) -> str:
        """Produce the mythic one-sentence compression (LLM or mock)."""
        model = settings.chronicler_model

        # --- Mock mode ---
        if model == "mock":
            await asyncio.sleep(0.2)
            return random.choice(_MOCK_CHRONICLES)

        # --- Real LLM mode ---
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
            sentence = raw.strip().rstrip(".") + "."  # normalize punctuation
            # Safety: truncate if LLM rambled
            if "\n" in sentence:
                sentence = sentence.split("\n")[0].strip()
            logger.info(f"Chronicle: {sentence}")
            return sentence
        except Exception as e:
            logger.error(f"Chronicler LLM failed: {e}. Using mock.")
            return random.choice(_MOCK_CHRONICLES)


def _dominant(state: ThreadState) -> str:
    """Quick dominant vector label."""
    v = state.soul_ledger.vectors
    pairs = [("metis", v.metis), ("bia", v.bia), ("kleos", v.kleos), ("aidos", v.aidos)]
    return max(pairs, key=lambda x: x[1])[0]
