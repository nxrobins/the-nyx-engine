"""Lachesis - The State Ledger & RAG Memory v2.1 (Responsibility Split).

'You are Lachesis. You are the strict memory of the system. Ingest the
player's action and compare it against their soul vectors, oaths, and
environment. Output a strict logical consequence in JSON format.'

Classifies player actions into soul vector deltas:
  - Cunning/deception/strategy → metis+
  - Force/violence/aggression → bia+
  - Boasting/glory-seeking/public acts → kleos+
  - Stealth/restraint/humility → aidos+

v2.1 — Oath detection and hamartia assignment extracted to standalone
service modules (oath_engine, hamartia_engine). Lachesis focuses on
LLM-dependent judgment: action validity, vector classification,
environment tracking, and outcome classification. The kernel owns
deterministic oath/hamartia logic directly.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import LachesisResponse, ThreadState
from app.services import llm
from app.services.prompt_loader import load_prompt

logger = logging.getLogger("nyx.lachesis")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/lachesis.yaml)
# ---------------------------------------------------------------------------

LACHESIS_SYSTEM_PROMPT = load_prompt("lachesis")


# ---------------------------------------------------------------------------
# Mock Logic (Phase 1 fallback)
# ---------------------------------------------------------------------------

def _mock_evaluate(state: ThreadState, action: str) -> LachesisResponse:
    """Keyword-based mock evaluation — deterministic fallback."""
    updated = copy.deepcopy(state)
    # NOTE: turn_count is managed by the kernel, not Lachesis
    updated.last_action = action

    action_lower = action.lower()

    # Invalid action detection
    if any(word in action_lower for word in ["fly", "teleport", "godmode"]):
        return LachesisResponse(
            valid_action=False,
            reason="Action exceeds mortal capabilities.",
            updated_state=updated,
        )

    # Classify action into vector deltas (oath/hamartia handled by kernel)

    # Combat / force → bia+
    if any(word in action_lower for word in ["attack", "fight", "strike", "stab", "smash"]):
        updated.last_outcome = "violent_triumph"
        updated.rag_context.append(
            f"Turn {updated.session.turn_count}: Player engaged in combat."
        )
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"bia": 2.0, "aidos": -0.5},
            environment_update=updated.session.current_environment,
        )

    # Cunning / deception → metis+
    if any(word in action_lower for word in ["deceive", "trick", "persuade", "convince", "lie"]):
        updated.last_outcome = "cunning_success"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"metis": 2.0, "kleos": 0.5},
            environment_update=updated.session.current_environment,
        )

    # Glory / boasting → kleos+
    if any(word in action_lower for word in ["boast", "proclaim", "challenge", "declare"]):
        updated.last_outcome = "glory_seized"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"kleos": 2.5, "aidos": -1.0},
            environment_update=updated.session.current_environment,
        )

    # Stealth / restraint → aidos+
    if any(word in action_lower for word in ["hide", "rest", "pray", "wait", "sneak", "observe"]):
        updated.last_outcome = "shadow_move"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"aidos": 2.0, "bia": -0.5},
            environment_update=updated.session.current_environment,
        )

    # Default: neutral
    updated.last_outcome = "neutral"
    return LachesisResponse(
        valid_action=True,
        updated_state=updated,
        vector_deltas={"metis": 0.5, "aidos": 0.5},
        environment_update=updated.session.current_environment,
    )


# ---------------------------------------------------------------------------
# Payload Builder
# ---------------------------------------------------------------------------

def _build_payload(state: ThreadState, action: str) -> str:
    """Build the structured JSON payload for Lachesis."""
    oaths_summary = [
        {"oath_id": o.oath_id, "text": o.text, "turn_sworn": o.turn_sworn}
        for o in state.soul_ledger.active_oaths
        if not o.broken
    ]

    recent_context = state.rag_context[-10:] if state.rag_context else []

    payload = {
        "player_action": action,
        "soul_vectors": state.soul_ledger.vectors.model_dump(),
        "hamartia": state.soul_ledger.hamartia,
        "active_oaths": oaths_summary,
        "environment": state.session.current_environment,
        "rag_context": recent_context,
        "turn_number": state.session.turn_count,  # kernel already incremented
        "player_name": state.session.player_name,
        "player_gender": state.session.player_gender,
    }

    msg = "JUDGE THE FOLLOWING ACTION:\n\n" + json.dumps(payload, indent=2)

    return msg


# ---------------------------------------------------------------------------
# Response Parsers (battle-tested from v1)
# ---------------------------------------------------------------------------

def _clean_json(raw: str) -> str:
    """Best-effort cleanup of slightly malformed JSON from fast LLMs."""
    cleaned = raw.strip()

    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    # Find JSON object boundaries
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    # Fix unterminated strings
    lines = cleaned.split("\n")
    fixed_lines = []
    for line in lines:
        quote_count = line.count('"') - line.count('\\"')
        if quote_count % 2 != 0:
            line = line.rstrip().rstrip(",")
            if not line.endswith('"'):
                line += '"'
            if not line.rstrip().endswith("}"):
                line += ","
        fixed_lines.append(line)
    cleaned = "\n".join(fixed_lines)

    # Remove trailing commas before closing braces
    cleaned = re.sub(r",\s*}", "}", cleaned)

    return cleaned


def _regex_extract(raw: str) -> dict:
    """Last-resort field extraction via regex when JSON is too broken."""
    data: dict = {}

    m = re.search(r'"valid_action"\s*:\s*(true|false)', raw, re.IGNORECASE)
    data["valid_action"] = m.group(1).lower() == "true" if m else True

    m = re.search(r'"reason"\s*:\s*"([^"]*)"', raw)
    data["reason"] = m.group(1) if m else ""

    m = re.search(r'"outcome_type"\s*:\s*"(\w+)"', raw)
    data["outcome_type"] = m.group(1) if m else "neutral"

    # Vector deltas — extract individually
    deltas: dict[str, float] = {}
    for vec in ("metis", "bia", "kleos", "aidos"):
        m = re.search(rf'"{vec}"\s*:\s*(-?[\d.]+)', raw)
        if m:
            deltas[vec] = float(m.group(1))
    data["vector_deltas"] = deltas

    m = re.search(r'"oath_detected"\s*:\s*"([^"]*)', raw)
    data["oath_detected"] = m.group(1) if m else None

    m = re.search(r'"oath_violation"\s*:\s*"([^"]*)', raw)
    data["oath_violation"] = m.group(1) if m else None

    m = re.search(r'"environment_update"\s*:\s*"([^"]*)', raw)
    data["environment_update"] = m.group(1) if m else ""

    m = re.search(r'"rag_summary"\s*:\s*"([^"]*)', raw)
    data["rag_summary"] = m.group(1) if m else ""

    m = re.search(r'"assigned_hamartia"\s*:\s*"([^"]*)', raw)
    data["assigned_hamartia"] = m.group(1) if m else None

    return data


def _clamp_deltas(deltas: dict[str, float]) -> dict[str, float]:
    """Enforce delta range [-2.0, +3.0] per vector."""
    return {
        k: max(-2.0, min(3.0, v))
        for k, v in deltas.items()
        if k in ("metis", "bia", "kleos", "aidos")
    }


def _infer_deltas_from_action(action: str) -> dict[str, float]:
    """Keyword-based fallback when LLM returns empty deltas."""
    a = action.lower()
    if any(w in a for w in ["attack", "fight", "strike", "smash", "punch", "kill"]):
        return {"bia": 2.0, "aidos": -0.5}
    if any(w in a for w in ["deceive", "trick", "persuade", "convince", "outsmart"]):
        return {"metis": 2.0, "kleos": 0.5}
    if any(w in a for w in ["boast", "proclaim", "challenge", "declare", "glory"]):
        return {"kleos": 2.5, "aidos": -1.0}
    if any(w in a for w in ["hide", "sneak", "rest", "pray", "observe", "wait"]):
        return {"aidos": 2.0, "bia": -0.5}
    return {"metis": 0.5, "aidos": 0.5}


def _parse_response(raw: str, state: ThreadState, action: str) -> LachesisResponse:
    """Parse the LLM's JSON response into a LachesisResponse with state updates."""
    cleaned = _clean_json(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed even after cleanup. Attempting regex extraction.")
        data = _regex_extract(cleaned)

    updated = copy.deepcopy(state)
    # NOTE: turn_count is managed by the kernel, not Lachesis
    updated.last_action = action

    valid = data.get("valid_action", True)

    if not valid:
        return LachesisResponse(
            valid_action=False,
            reason=data.get("reason", "Action denied by Lachesis."),
            updated_state=updated,
        )

    # Extract and clamp vector deltas
    raw_deltas = data.get("vector_deltas", {})
    if not raw_deltas or not isinstance(raw_deltas, dict):
        raw_deltas = _infer_deltas_from_action(action)
        logger.info("Lachesis: LLM returned empty deltas, using keyword inference.")
    vector_deltas = _clamp_deltas(raw_deltas)

    # Set outcome type
    outcome_type = data.get("outcome_type", "neutral")
    updated.last_outcome = outcome_type

    # Environment update
    env_update = data.get("environment_update", "")
    if env_update:
        updated.session.current_environment = env_update

    # RAG entry
    rag_summary = data.get("rag_summary", "")
    if not rag_summary:
        rag_summary = f"Player attempted: {action[:80]}. Outcome: {outcome_type}."
        logger.info("Lachesis: LLM omitted rag_summary, using fallback.")
    updated.rag_context.append(f"Turn {updated.session.turn_count}: {rag_summary}")

    # Oath detection — pass through from LLM (kernel handles deterministic fallback)
    oath_detected = data.get("oath_detected")

    # Oath violation — pass through from LLM
    oath_violation = data.get("oath_violation")

    # Hamartia — pass through from LLM (kernel handles deterministic fallback)
    assigned_hamartia = data.get("assigned_hamartia")

    return LachesisResponse(
        valid_action=True,
        updated_state=updated,
        vector_deltas=vector_deltas,
        oath_detected=oath_detected,
        oath_violation=oath_violation,
        environment_update=env_update,
        assigned_hamartia=assigned_hamartia,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Lachesis(AgentBase):
    name = "lachesis"

    async def evaluate(
        self, state: ThreadState, action: str
    ) -> LachesisResponse:
        model = settings.lachesis_model

        # --- Mock mode ---
        if model == "mock":
            await asyncio.sleep(0.3)
            return _mock_evaluate(state, action)

        # --- Real LLM mode ---
        user_message = _build_payload(state, action)
        logger.info(f"Lachesis calling {model}")

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=LACHESIS_SYSTEM_PROMPT,
                user_message=user_message,
                temperature=0.3,
                max_tokens=500,
                json_mode=("anthropic" not in model),
            )
            logger.info(f"Lachesis got {len(raw)} chars from {model}")
            logger.debug(f"Lachesis raw response: {raw[:500]}")

            result = _parse_response(raw, state, action)
            logger.info(
                f"Lachesis verdict: valid={result.valid_action}, "
                f"deltas={result.vector_deltas}, "
                f"oath={result.oath_detected is not None}"
            )
            return result

        except Exception as e:
            logger.error(f"Lachesis LLM failed: {e}. Falling back to mock.")
            return _mock_evaluate(state, action)
