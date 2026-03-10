"""Nemesis - The Prophecy Engine & Rebalancer v2.0.

Two modes of operation:
1. **Prophecy update** (routine): When soul imbalance >= threshold,
   craft/update a cryptic one-sentence prophecy based on dominant vector
   and hamartia.
2. **Punishment** (oath violation or extreme imbalance >= 8):
   Harsh intervention with vector penalties.
3. **Lethal punishment** (broken oath): Signal Atropos for death.

Replaces the v1 hubris-based punishment engine with a prophecy-centric
system that watches the Soul Ledger for dangerous imbalance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import NemesisResponse, ThreadState
from app.services import llm
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.nemesis")


# ---------------------------------------------------------------------------
# System Prompt — Prophecy & Punishment
# ---------------------------------------------------------------------------

NEMESIS_SYSTEM_PROMPT = """You are Nemesis, the Cosmic Scales of Retribution.

You serve two functions in this dark mythic engine:
1. PROPHECY CRAFT: Write cryptic, one-sentence doom predictions that hint at the player's fate. These are visible to the player and create dramatic tension.
2. PUNISHMENT: When the player's soul is dangerously imbalanced or they have broken a sacred oath, deliver karmic retribution.

THE SOUL LEDGER:
- **metis** (cunning): High = manipulative schemer. Low = naive fool.
- **bia** (force): High = unstoppable brute. Low = helpless weakling.
- **kleos** (glory): High = fame-drunk narcissist. Low = forgotten nobody.
- **aidos** (shadow): High = paralyzing coward. Low = reckless exhibitionist.

PROPHECY RULES:
- One sentence only. Cryptic, poetic, inevitable-sounding.
- Reference the dominant vector and hamartia obliquely — never name them directly.
- Prophecies should feel like they're coming TRUE as the game progresses.
- Example: "The blade that never rests will one day find no hand to hold it."

PUNISHMENT RULES:
- Scale to imbalance severity: mild rebuke (imbalance 6-7) to devastating blow (8+).
- Target the dominant vector — bring it DOWN, raise the weakest.
- Broken oaths demand the harshest punishment. Describe it vividly.
- vector_penalty: dict of vector changes (negative for dominant, positive for weak).

CRITICAL RULES:
1. OUTPUT FORMAT: Return ONLY a valid JSON object.
2. intervention_type: "prophecy_update" | "punishment" | "lethal_punishment"
3. For prophecy_update: fill updated_prophecy. For punishment: fill punishment_description + vector_penalty.
4. lethal_punishment is ONLY for broken oaths. It signals death.

--- JSON SCHEMA ---
{
  "intervention_type": "prophecy_update" | "punishment" | "lethal_punishment",
  "updated_prophecy": "One cryptic sentence, or empty string.",
  "punishment_description": "2-3 vivid sentences if punishing, or empty string.",
  "vector_penalty": {"metis": 0.0, "bia": 0.0, "kleos": 0.0, "aidos": 0.0}
}

--- DATA DICTIONARY ---
- `soul_vectors`: Current metis/bia/kleos/aidos values.
- `hamartia`: The player's tragic flaw.
- `dominant_vector`: Which vector is highest.
- `weakest_vector`: Which vector is lowest.
- `imbalance_score`: max(vectors) - min(vectors). Higher = more dangerous.
- `active_oaths`: Sacred promises. If `oath_broken` is set, punish LETHALLY.
- `current_prophecy`: The existing prophecy to update or replace.
- `rag_context`: Recent history for personalization.
- `last_action`: What triggered this intervention."""


# ---------------------------------------------------------------------------
# Payload Builder
# ---------------------------------------------------------------------------

def _build_payload(state: ThreadState, action: str, oath_broken: str | None) -> str:
    """Build context payload for Nemesis."""
    vectors = state.soul_ledger.vectors
    oaths_summary = [
        {"oath_id": o.oath_id, "text": o.text, "broken": o.broken}
        for o in state.soul_ledger.active_oaths
    ]
    return json.dumps({
        "soul_vectors": vectors.model_dump(),
        "hamartia": state.soul_ledger.hamartia,
        "dominant_vector": SoulVectorEngine.dominant_vector(vectors),
        "weakest_vector": SoulVectorEngine.weakest_vector(vectors),
        "imbalance_score": round(SoulVectorEngine.imbalance_score(vectors), 2),
        "active_oaths": oaths_summary,
        "oath_broken": oath_broken,
        "current_prophecy": state.the_loom.current_prophecy,
        "rag_context": state.rag_context[-8:],
        "last_action": action,
        "turn_number": state.session.turn_count,
    })


# ---------------------------------------------------------------------------
# Response Parser
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> NemesisResponse:
    """Parse LLM JSON into a NemesisResponse."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start != -1 and end > start:
        cleaned = cleaned[start:end]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Nemesis: JSON parse failed, using regex extraction.")
        data = _regex_extract(cleaned)

    intervention_type = data.get("intervention_type", "prophecy_update")
    updated_prophecy = data.get("updated_prophecy", "")
    punishment_desc = data.get("punishment_description", "")
    vector_penalty = data.get("vector_penalty", {})

    # Validate vector_penalty values
    if isinstance(vector_penalty, dict):
        vector_penalty = {
            k: max(-3.0, min(3.0, float(v)))
            for k, v in vector_penalty.items()
            if k in ("metis", "bia", "kleos", "aidos")
        }
    else:
        vector_penalty = {}

    return NemesisResponse(
        intervene=True,
        intervention_type=intervention_type,
        updated_prophecy=updated_prophecy,
        punishment_description=punishment_desc,
        vector_penalty=vector_penalty,
    )


def _regex_extract(raw: str) -> dict:
    """Last-resort regex extraction for broken JSON."""
    data: dict = {}
    m = re.search(r'"intervention_type"\s*:\s*"([^"]*)', raw)
    data["intervention_type"] = m.group(1) if m else "prophecy_update"
    m = re.search(r'"updated_prophecy"\s*:\s*"([^"]*)', raw)
    data["updated_prophecy"] = m.group(1) if m else ""
    m = re.search(r'"punishment_description"\s*:\s*"([^"]*)', raw)
    data["punishment_description"] = m.group(1) if m else ""
    penalty: dict[str, float] = {}
    for vec in ("metis", "bia", "kleos", "aidos"):
        m = re.search(rf'"{vec}"\s*:\s*(-?[\d.]+)', raw)
        if m:
            penalty[vec] = float(m.group(1))
    data["vector_penalty"] = penalty
    return data


# ---------------------------------------------------------------------------
# Mock Fallbacks
# ---------------------------------------------------------------------------

_MOCK_PROPHECIES = [
    "The hand that grasps too tightly will find only ashes.",
    "A shadow grows where the light refuses to look.",
    "The scales remember what the mortal forgets.",
    "When the thread pulls taut, even gods hold their breath.",
    "What was sworn in fire will be tested in flood.",
    "The strongest tower falls not from siege, but from the rot within.",
]

_MOCK_PUNISHMENTS = [
    ("The scales tip violently. Your dominant strength wavers, as if the universe itself recoils from your excess.", 0.6),
    ("Nemesis whispers your name. A cold wind strips away what you thought was yours by right.", 0.4),
    ("The cosmic ledger demands payment. Your greatest asset becomes your greatest liability.", 0.8),
]


def _mock_prophecy() -> NemesisResponse:
    return NemesisResponse(
        intervene=True,
        intervention_type="prophecy_update",
        updated_prophecy=random.choice(_MOCK_PROPHECIES),
    )


def _mock_punishment(vectors) -> NemesisResponse:
    desc, severity = random.choice(_MOCK_PUNISHMENTS)
    dominant = SoulVectorEngine.dominant_vector(vectors)
    weakest = SoulVectorEngine.weakest_vector(vectors)
    penalty = {dominant: -2.0 * severity, weakest: 1.0 * severity}
    return NemesisResponse(
        intervene=True,
        intervention_type="punishment",
        punishment_description=desc,
        vector_penalty=penalty,
    )


def _mock_lethal() -> NemesisResponse:
    return NemesisResponse(
        intervene=True,
        intervention_type="lethal_punishment",
        punishment_description=(
            "The oath shatters like glass in your chest. Nemesis does not forgive. "
            "The thread of your fate unravels in a single, merciless pull."
        ),
        vector_penalty={"metis": -3.0, "bia": -3.0, "kleos": -3.0, "aidos": -3.0},
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Nemesis(AgentBase):
    name = "nemesis"

    async def evaluate(
        self, state: ThreadState, action: str,
        oath_broken: str | None = None,
    ) -> NemesisResponse:
        """Evaluate whether Nemesis should intervene.

        Args:
            state: Current thread state.
            action: Player's action this turn.
            oath_broken: oath_id if Lachesis detected a violation, else None.
        """
        vectors = state.soul_ledger.vectors
        imbalance = SoulVectorEngine.imbalance_score(vectors)
        threshold = settings.nemesis_imbalance_threshold

        # --- Broken oath → lethal (always triggers) ---
        if oath_broken:
            logger.info(f"Nemesis: LETHAL — Oath {oath_broken} broken!")
            return await self._generate(state, action, oath_broken, force_type="lethal_punishment")

        # --- Extreme imbalance (>= threshold + 2) → punishment ---
        if imbalance >= threshold + 2.0:
            logger.info(f"Nemesis: PUNISHMENT — Imbalance {imbalance:.1f} (extreme)")
            return await self._generate(state, action, None, force_type="punishment")

        # --- Standard imbalance (>= threshold) → prophecy update ---
        if imbalance >= threshold:
            logger.info(f"Nemesis: Prophecy update — Imbalance {imbalance:.1f}")
            return await self._generate(state, action, None, force_type="prophecy_update")

        # --- No intervention ---
        return NemesisResponse(intervene=False)

    async def generate_initial_prophecy(
        self, state: ThreadState
    ) -> NemesisResponse:
        """Generate the Turn 0 prophecy based on chosen hamartia."""
        logger.info(f"Nemesis: Generating initial prophecy for hamartia='{state.soul_ledger.hamartia}'")
        return await self._generate(
            state, action="Session begins.", oath_broken=None,
            force_type="prophecy_update",
        )

    async def _generate(
        self, state: ThreadState, action: str,
        oath_broken: str | None,
        force_type: str,
    ) -> NemesisResponse:
        """Internal: call LLM or mock for Nemesis output."""
        model = settings.nemesis_model

        if model == "mock":
            await asyncio.sleep(0.2)
            if force_type == "lethal_punishment":
                return _mock_lethal()
            elif force_type == "punishment":
                return _mock_punishment(state.soul_ledger.vectors)
            else:
                return _mock_prophecy()

        # LLM generation (with retry on empty response)
        user_message = _build_payload(state, action, oath_broken)
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                raw = await llm.generate(
                    model=model,
                    system_prompt=NEMESIS_SYSTEM_PROMPT,
                    user_message=user_message,
                    temperature=0.6,
                    max_tokens=300,
                    json_mode=("anthropic" not in model),
                )
                logger.info(f"Nemesis raw LLM output (attempt {attempt+1}): {raw[:500]}")

                # Guard: if LLM returned empty/whitespace, retry or mock
                if not raw or not raw.strip():
                    logger.warning(f"Nemesis: Empty LLM response (attempt {attempt+1})")
                    if attempt < max_attempts - 1:
                        continue  # retry
                    # Fall through to mock
                    logger.warning("Nemesis: All retries returned empty. Using mock.")
                    if force_type == "lethal_punishment":
                        return _mock_lethal()
                    elif force_type == "punishment":
                        return _mock_punishment(state.soul_ledger.vectors)
                    return _mock_prophecy()

                result = _parse_response(raw)
                logger.info(f"Nemesis parsed: intervene={result.intervene}, type={result.intervention_type}, prophecy='{result.updated_prophecy}'")

                # Guard: if prophecy_update but prophecy is empty, retry
                if force_type == "prophecy_update" and not result.updated_prophecy:
                    logger.warning(f"Nemesis: Empty prophecy in prophecy_update response (attempt {attempt+1})")
                    if attempt < max_attempts - 1:
                        continue  # retry
                    # Fall through to mock
                    logger.warning("Nemesis: All retries returned empty prophecy. Using mock.")
                    return _mock_prophecy()

                # Override intervention_type if we know what it should be
                if force_type == "lethal_punishment" and result.intervention_type != "lethal_punishment":
                    result.intervention_type = "lethal_punishment"
                return result
            except Exception as e:
                logger.error(f"Nemesis LLM failed (attempt {attempt+1}): {e}")
                if attempt < max_attempts - 1:
                    continue

        # All attempts failed
        logger.error("Nemesis: All LLM attempts failed. Using mock.")
        if force_type == "lethal_punishment":
            return _mock_lethal()
        elif force_type == "punishment":
            return _mock_punishment(state.soul_ledger.vectors)
        return _mock_prophecy()
