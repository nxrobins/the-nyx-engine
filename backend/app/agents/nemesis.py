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
from app.schemas.state import AgentProposal, NemesisResponse, ThreadState
from app.services import llm
from app.services.canon import render_scene_snapshot
from app.services.oath_engine import oath_hypocrisy_score
from app.services.pressure import pressure_summary
from app.services.prompt_loader import load_prompt
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.nemesis")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/nemesis.yaml)
# ---------------------------------------------------------------------------

NEMESIS_SYSTEM_PROMPT = load_prompt("nemesis")


def _pressure_patch_for_response(
    response: NemesisResponse,
    hypocrisy_score: float = 0.0,
) -> dict[str, float]:
    if not response.intervene:
        return {}

    patch = {"omen": 0.4}
    if response.intervention_type == "punishment":
        patch.update({"suspicion": 0.3, "exploit_score": 0.5, "omen": 0.8})
    elif response.intervention_type == "lethal_punishment":
        patch.update(
            {"suspicion": 0.8, "faction_heat": 0.6, "exploit_score": 1.0, "omen": 1.0}
        )
    if hypocrisy_score > 0:
        patch["suspicion"] = patch.get("suspicion", 0.0) + min(hypocrisy_score * 0.3, 0.6)
    return {key: round(value, 2) for key, value in patch.items()}


def _attach_proposal(
    response: NemesisResponse,
    *,
    hypocrisy_score: float = 0.0,
) -> NemesisResponse:
    """Attach a structured proposal to a Nemesis response."""
    scene_patch: dict[str, object] = {}
    if response.intervention_type:
        scene_patch["intervention_type"] = response.intervention_type
    if response.updated_prophecy:
        scene_patch["updated_prophecy"] = response.updated_prophecy
    if response.punishment_description:
        scene_patch["punishment_description"] = response.punishment_description

    response.proposal = AgentProposal(
        agent="nemesis",
        allow_action=True,
        scene_patch=scene_patch,
        vector_patch=dict(response.vector_penalty),
        pressure_patch=_pressure_patch_for_response(response, hypocrisy_score),
        prophecy_patch=response.updated_prophecy,
        intervention_copy=response.punishment_description or response.updated_prophecy,
        priority_note="Judgment, prophecy, and karmic rebalancing.",
        confidence=0.85 if response.intervene else 0.45,
    )
    return response


# ---------------------------------------------------------------------------
# Payload Builder
# ---------------------------------------------------------------------------

def _build_payload(state: ThreadState, action: str, oath_broken: str | None) -> str:
    """Build context payload for Nemesis."""
    vectors = state.soul_ledger.vectors
    scene_snapshot = render_scene_snapshot(state)
    oaths_summary = [
        {
            "oath_id": o.oath_id,
            "text": o.text,
            "broken": o.broken,
            "status": o.status,
            "terms": o.terms.model_dump() if o.terms else None,
        }
        for o in state.soul_ledger.active_oaths
    ]
    return json.dumps({
        "soul_vectors": vectors.model_dump(),
        "hamartia": state.soul_ledger.hamartia,
        "hamartia_profile": (
            state.soul_ledger.hamartia_profile.model_dump()
            if state.soul_ledger.hamartia_profile else None
        ),
        "dominant_vector": SoulVectorEngine.dominant_vector(vectors),
        "weakest_vector": SoulVectorEngine.weakest_vector(vectors),
        "imbalance_score": round(SoulVectorEngine.imbalance_score(vectors), 2),
        "pressures": state.pressures.model_dump(),
        "pressure_summary": pressure_summary(state),
        "active_oaths": oaths_summary,
        "oath_broken": oath_broken,
        "current_prophecy": state.the_loom.current_prophecy,
        "scene_snapshot": scene_snapshot or None,
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
        profile = state.soul_ledger.hamartia_profile
        hypocrisy = oath_hypocrisy_score(state.soul_ledger.active_oaths, action)
        lowered_action = action.lower()

        effective_imbalance = imbalance * (
            profile.nemesis_multiplier if profile is not None else 1.0
        )
        if profile and "violent" in profile.choice_bias and any(
            word in lowered_action for word in ("attack", "strike", "stab", "kill", "fight")
        ):
            effective_imbalance += 1.0
        if profile and "public" in profile.choice_bias and any(
            word in lowered_action for word in ("declare", "challenge", "boast", "shout")
        ):
            effective_imbalance += 0.5

        exploit = state.pressures.exploit_score
        suspicion = state.pressures.suspicion
        omen = state.pressures.omen
        faction_heat = state.pressures.faction_heat

        # --- Broken oath → lethal (always triggers) ---
        if oath_broken:
            logger.info(f"Nemesis: LETHAL — Oath {oath_broken} broken!")
            result = await self._generate(state, action, oath_broken, force_type="lethal_punishment")
            return _attach_proposal(result, hypocrisy_score=max(hypocrisy, 1.0))

        # --- Patterned abuse, public shame, or extreme imbalance → punishment ---
        if (
            effective_imbalance >= threshold + 1.5
            or exploit >= 2.0
            or suspicion >= 2.75
            or faction_heat >= 2.5
            or hypocrisy >= 1.0
        ):
            logger.info(
                "Nemesis: PUNISHMENT — "
                f"effective_imbalance={effective_imbalance:.1f}, exploit={exploit:.1f}, "
                f"suspicion={suspicion:.1f}, hypocrisy={hypocrisy:.1f}"
            )
            result = await self._generate(state, action, None, force_type="punishment")
            return _attach_proposal(result, hypocrisy_score=hypocrisy)

        # --- Lower-level prophetic warning ---
        if (
            effective_imbalance >= threshold
            or exploit >= 1.25
            or omen >= 1.5
            or hypocrisy >= 0.5
        ):
            logger.info(
                "Nemesis: Prophecy update — "
                f"effective_imbalance={effective_imbalance:.1f}, omen={omen:.1f}, "
                f"exploit={exploit:.1f}"
            )
            result = await self._generate(state, action, None, force_type="prophecy_update")
            return _attach_proposal(result, hypocrisy_score=hypocrisy)

        # --- No intervention ---
        return _attach_proposal(NemesisResponse(intervene=False), hypocrisy_score=hypocrisy)

    async def generate_initial_prophecy(
        self, state: ThreadState
    ) -> NemesisResponse:
        """Generate the Turn 0 prophecy based on chosen hamartia."""
        logger.info(f"Nemesis: Generating initial prophecy for hamartia='{state.soul_ledger.hamartia}'")
        result = await self._generate(
            state, action="Session begins.", oath_broken=None,
            force_type="prophecy_update",
        )
        return _attach_proposal(result)

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
