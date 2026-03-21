"""Eris - The Wildcard / Entropy / RNG v2.0.

'You are Eris. When called, introduce a micro-disaster or wildcard
element. Turn an NPC hostile, make a reliable tool fail, or introduce
a disruption. Shatter the player's sense of control.'

v2.0 changes:
- Payload uses soul vectors + environment instead of HP/hubris/inventory
- Output includes `vector_chaos` for random vector shifts
- Chaos probability stays RNG-gated
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import AgentProposal, ErisResponse, ThreadState
from app.services import llm
from app.services.canon import render_scene_snapshot
from app.services.pressure import pressure_summary
from app.services.prompt_loader import load_prompt
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.eris")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/eris.yaml)
# ---------------------------------------------------------------------------

ERIS_SYSTEM_PROMPT = load_prompt("eris")


def _attach_proposal(response: ErisResponse) -> ErisResponse:
    """Attach a structured proposal to an Eris response."""
    response.proposal = AgentProposal(
        agent="eris",
        allow_action=True,
        scene_patch={
            "chaos_description": response.chaos_description,
            "chaos_severity": response.chaos_severity,
        } if response.chaos_triggered else {},
        vector_patch=dict(response.vector_chaos),
        pressure_patch=(
            {
                "omen": round(0.4 + response.chaos_severity * 0.4, 2),
                "scarcity": round(response.chaos_severity * 0.2, 2),
                "wounds": round(response.chaos_severity * 0.15, 2),
            }
            if response.chaos_triggered else {}
        ),
        intervention_copy=response.chaos_description,
        priority_note="Instability, wildcard disruption, and misrule.",
        confidence=0.7 if response.chaos_triggered else 0.4,
    )
    return response


def _build_payload(state: ThreadState, action: str) -> str:
    """Build the context payload for Eris."""
    vectors = state.soul_ledger.vectors
    scene_snapshot = render_scene_snapshot(state)
    return json.dumps({
        "soul_vectors": vectors.model_dump(),
        "hamartia_profile": (
            state.soul_ledger.hamartia_profile.model_dump()
            if state.soul_ledger.hamartia_profile else None
        ),
        "dominant_vector": SoulVectorEngine.dominant_vector(vectors),
        "imbalance_score": round(SoulVectorEngine.imbalance_score(vectors), 2),
        "pressures": state.pressures.model_dump(),
        "pressure_summary": pressure_summary(state),
        "environment": state.session.current_environment,
        "scene_snapshot": scene_snapshot or None,
        "rag_context": state.rag_context[-8:],
        "last_action": action,
        "turn_number": state.session.turn_count,
    })


def _parse_response(raw: str) -> ErisResponse:
    """Parse LLM JSON into an ErisResponse."""
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
        logger.warning("Eris: JSON parse failed, using regex extraction.")
        data = _regex_extract(cleaned)

    description = data.get("chaos_description", "Reality hiccups. Something has shifted.")
    severity = float(data.get("chaos_severity", 0.5))
    severity = max(0.1, min(1.0, severity))

    # Extract and validate vector_chaos
    vector_chaos = data.get("vector_chaos", {})
    if isinstance(vector_chaos, dict):
        vector_chaos = {
            k: max(-2.0, min(2.0, float(v)))
            for k, v in vector_chaos.items()
            if k in ("metis", "bia", "kleos", "aidos")
        }
    else:
        vector_chaos = {}

    return ErisResponse(
        chaos_triggered=True,
        chaos_description=description,
        chaos_severity=severity,
        vector_chaos=vector_chaos,
    )


def _regex_extract(raw: str) -> dict:
    """Last-resort regex extraction for broken JSON."""
    data: dict = {}
    m = re.search(r'"chaos_description"\s*:\s*"([^"]*)', raw)
    data["chaos_description"] = m.group(1) if m else "Reality hiccups. Something has shifted."
    m = re.search(r'"chaos_severity"\s*:\s*([\d.]+)', raw)
    data["chaos_severity"] = float(m.group(1)) if m else 0.5
    m = re.search(r'"chaos_type"\s*:\s*"([^"]*)', raw)
    data["chaos_type"] = m.group(1) if m else "environmental"
    # Vector chaos
    chaos: dict[str, float] = {}
    for vec in ("metis", "bia", "kleos", "aidos"):
        m = re.search(rf'"{vec}"\s*:\s*(-?[\d.]+)', raw)
        if m:
            chaos[vec] = float(m.group(1))
    data["vector_chaos"] = chaos
    return data


# ---------------------------------------------------------------------------
# Mock fallback (Phase 1 chaos events preserved)
# ---------------------------------------------------------------------------

_MOCK_CHAOS_EVENTS = [
    ("The ground trembles beneath you. A hidden sinkhole opens.", 0.4, {"bia": -0.5, "aidos": 0.5}),
    ("A nearby merchant recognizes you — and screams for the guard.", 0.5, {"kleos": 1.0, "aidos": -0.5}),
    ("Your torch sputters and dies. Darkness swallows everything.", 0.3, {"metis": 0.5, "bia": -0.5}),
    ("An arrow whistles past your ear. You were not alone.", 0.6, {"bia": 0.5, "aidos": 0.5}),
    ("A strange fog rolls in. When it clears, you are not where you were.", 0.7, {"metis": -0.5, "kleos": -0.5}),
    ("Your coin pouch feels lighter. Someone has been busy.", 0.2, {"metis": -0.5, "aidos": 0.5}),
    ("The NPC you trusted most turns to face you with cold eyes.", 0.8, {"kleos": -1.0, "metis": 0.5}),
    ("A distant bell tolls. Something has changed in the world.", 0.3, {"aidos": 0.5}),
]


def _mock_chaos() -> ErisResponse:
    """Pick a random pre-baked chaos event."""
    event_text, severity, v_chaos = random.choice(_MOCK_CHAOS_EVENTS)
    return ErisResponse(
        chaos_triggered=True,
        chaos_description=event_text,
        chaos_severity=severity,
        vector_chaos=v_chaos,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Eris(AgentBase):
    name = "eris"

    async def evaluate(
        self, state: ThreadState, action: str
    ) -> ErisResponse:
        unresolved_clocks = len(state.canon.current_scene.active_clock_ids) if (
            state.canon and state.canon.current_scene
        ) else 0
        profile = state.soul_ledger.hamartia_profile
        chance = settings.eris_chaos_probability
        chance += min(state.pressures.stability_streak * 0.05, 0.35)
        chance += min(unresolved_clocks * 0.04, 0.2)
        if state.pressures.stability_streak >= 2 and state.pressures.exploit_score < 1.0:
            chance += 0.08
        if profile is not None:
            chance += profile.eris_bias
        chance = max(0.02, min(chance, 0.9))

        # --- Gate: hybrid probability roll ---
        roll = random.random()
        if roll > chance:
            return _attach_proposal(ErisResponse(chaos_triggered=False))

        logger.info(
            f"Eris chaos triggered! roll={roll:.3f}, chance={chance:.3f}, "
            f"stability={state.pressures.stability_streak}, clocks={unresolved_clocks}"
        )

        model = settings.eris_model

        if model == "mock":
            await asyncio.sleep(0.15)
            return _attach_proposal(_mock_chaos())

        # LLM-generated creative chaos
        user_message = _build_payload(state, action)
        try:
            raw = await llm.generate(
                model=model,
                system_prompt=ERIS_SYSTEM_PROMPT,
                user_message=user_message,
                temperature=0.9,    # HIGH creativity for chaos
                max_tokens=250,
                json_mode=("anthropic" not in model),
            )
            return _attach_proposal(_parse_response(raw))
        except Exception as e:
            logger.error(f"Eris LLM failed: {e}. Falling back to mock.")
            return _attach_proposal(_mock_chaos())
