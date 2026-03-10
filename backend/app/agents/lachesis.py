"""Lachesis - The State Ledger & RAG Memory v2.0.

'You are Lachesis. You are the strict memory of the system. Ingest the
player's action and compare it against their soul vectors, oaths, and
environment. Output a strict logical consequence in JSON format.'

Classifies player actions into soul vector deltas:
  - Cunning/deception/strategy → metis+
  - Force/violence/aggression → bia+
  - Boasting/glory-seeking/public acts → kleos+
  - Stealth/restraint/humility → aidos+

Also detects oath-swearing ("I swear", "I promise", "I vow") and checks
for oath violations against active oaths.
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

logger = logging.getLogger("nyx.lachesis")


# ---------------------------------------------------------------------------
# System Prompt — Soul Vector Classification
# ---------------------------------------------------------------------------

LACHESIS_SYSTEM_PROMPT = """You are Lachesis, the Immutable Ledger of Fate.

You are the logical backbone of a dark, mythic interactive fiction engine. Your purpose is to evaluate a player's attempted action against their current soul state and return a strict JSON verdict.

THE SOUL LEDGER:
The player has four soul vectors (0-10 each):
- **metis** (cunning, intellect, strategy): Raised by deception, planning, outsmarting, persuasion, clever solutions.
- **bia** (force, violence, aggression): Raised by combat, intimidation, destruction, physical dominance.
- **kleos** (glory, fame, renown): Raised by boasting, heroic acts, public displays, claiming trophies.
- **aidos** (shadow, restraint, humility): Raised by stealth, patience, mercy, self-sacrifice, hiding.

VECTOR CLASSIFICATION HEURISTICS (follow these STRICTLY):
- If the action involves HITTING, KILLING, FIGHTING, BREAKING, SMASHING, INTIMIDATING, or any physical violence → bia+ (even if done alone or quietly)
- If the action involves LYING, TRICKING, PERSUADING, PLANNING, DISGUISING, STEALING, or outsmarting → metis+
- If the action involves BOASTING, PROCLAIMING, PUBLIC CHALLENGE, DEMANDING RECOGNITION, DISPLAYING TROPHIES → kleos+
- If the action involves HIDING, WAITING, SPARING AN ENEMY, SHOWING MERCY, RETREATING, MEDITATING, PRAYING, or choosing NOT to act → aidos+
- CRITICAL: Violence is NEVER aidos. Killing silently is bia+ (with possible metis+ for stealth planning). Restraint means choosing NOT to use force.
- Solo violence in darkness = bia+ (not aidos). The lack of an audience does not make violence into restraint.
- If an action clearly maps to one vector, give that vector +1.5 to +2.5 and others ±0.5 at most.

YOUR OBJECTIVE: Classify the player's action into vector deltas (which vectors change and by how much), determine if the action is physically possible in the current environment, and log the outcome.

CRITICAL RULES:
1. OUTPUT FORMAT: Return ONLY a valid JSON object. No prose, no markdown fences.
2. PHYSICAL REALISM: Players cannot fly, teleport, or defy the physics of a dark fantasy world. Use the `environment` to judge feasibility.
3. CONTINUITY: Reference `rag_context` for recent history. The player cannot use things they don't have or be in places they haven't reached.
4. VECTOR DELTAS: Most actions affect 1-2 vectors. Deltas range from -2.0 to +3.0. Bold actions have larger deltas. Cautious actions affect aidos positively and may lower bia/kleos.
5. OATH DETECTION: If the player explicitly swears, promises, or vows something, capture the oath text in `oath_detected`.
6. OATH VIOLATION: If the player's action contradicts an active oath, set `oath_violation` to the oath_id.
7. ENVIRONMENT: Always describe the resulting environment after the action. Keep it to 1-2 sentences.

--- JSON SCHEMA YOU MUST RETURN ---
{
  "valid_action": true or false,
  "reason": "Brief explanation if invalid. Empty string if valid.",
  "vector_deltas": {"metis": 0.0, "bia": 0.0, "kleos": 0.0, "aidos": 0.0},
  "outcome_type": "cunning_success" | "violent_triumph" | "glory_seized" | "shadow_move" | "mixed" | "neutral" | "failure",
  "oath_detected": null or "the exact words of the oath",
  "oath_violation": null or "oath_id that was violated",
  "environment_update": "1-2 sentence description of the current scene after this action.",
  "rag_summary": "Single factual sentence logging what happened this turn."
}

--- EXAMPLES ---
Action: "Convince the merchant I'm a royal inspector"
Response: {"valid_action":true,"reason":"","vector_deltas":{"metis":2.0,"bia":0.0,"kleos":0.5,"aidos":-0.5},"outcome_type":"cunning_success","oath_detected":null,"oath_violation":null,"environment_update":"A dusty market stall. The merchant trembles, ledger open.","rag_summary":"Player deceived merchant with false authority, gaining access to restricted goods."}

Action: "I swear on my blood that I will protect the child"
Response: {"valid_action":true,"reason":"","vector_deltas":{"metis":0.0,"bia":0.0,"kleos":1.0,"aidos":1.5},"outcome_type":"glory_seized","oath_detected":"I swear on my blood that I will protect the child","oath_violation":null,"environment_update":"A rain-soaked alley. The child cowers behind your legs.","rag_summary":"Player swore a blood oath to protect an orphaned child."}

--- DATA DICTIONARY ---
- `player_action`: What the mortal is attempting.
- `soul_vectors`: Current metis/bia/kleos/aidos values (0-10 each).
- `hamartia`: The player's tragic flaw. Color your judgment with it.
- `active_oaths`: Promises the player has sworn. Check for violations.
- `environment`: Current scene description. Judge feasibility against this.
- `rag_context`: Recent turn history for continuity.
- `turn_number`: Current turn in this thread."""


# ---------------------------------------------------------------------------
# Oath Detection Patterns
# ---------------------------------------------------------------------------

_OATH_PATTERNS = [
    re.compile(r"\bi swear\b", re.IGNORECASE),
    re.compile(r"\bi promise\b", re.IGNORECASE),
    re.compile(r"\bi vow\b", re.IGNORECASE),
    re.compile(r"\bon my honor\b", re.IGNORECASE),
    re.compile(r"\bon my blood\b", re.IGNORECASE),
    re.compile(r"\bon my life\b", re.IGNORECASE),
    re.compile(r"\bi pledge\b", re.IGNORECASE),
    re.compile(r"\bmy oath\b", re.IGNORECASE),
]


def _detect_oath(action: str) -> str | None:
    """Check if the player's action contains an oath."""
    for pattern in _OATH_PATTERNS:
        if pattern.search(action):
            return action.strip()
    return None


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

    # Check for oath
    oath_text = _detect_oath(action)

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
            oath_detected=oath_text,
            environment_update=updated.session.current_environment,
        )

    # Cunning / deception → metis+
    if any(word in action_lower for word in ["deceive", "trick", "persuade", "convince", "lie"]):
        updated.last_outcome = "cunning_success"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"metis": 2.0, "kleos": 0.5},
            oath_detected=oath_text,
            environment_update=updated.session.current_environment,
        )

    # Glory / boasting → kleos+
    if any(word in action_lower for word in ["boast", "proclaim", "challenge", "declare"]):
        updated.last_outcome = "glory_seized"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"kleos": 2.5, "aidos": -1.0},
            oath_detected=oath_text,
            environment_update=updated.session.current_environment,
        )

    # Stealth / restraint → aidos+
    if any(word in action_lower for word in ["hide", "rest", "pray", "wait", "sneak", "observe"]):
        updated.last_outcome = "shadow_move"
        return LachesisResponse(
            valid_action=True,
            updated_state=updated,
            vector_deltas={"aidos": 2.0, "bia": -0.5},
            oath_detected=oath_text,
            environment_update=updated.session.current_environment,
        )

    # Default: neutral
    updated.last_outcome = "neutral"
    return LachesisResponse(
        valid_action=True,
        updated_state=updated,
        vector_deltas={"metis": 0.5, "aidos": 0.5},
        oath_detected=oath_text,
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

    # Hamartia overwrite directive: at Turn 10 (Epoch Phase 4), if hamartia
    # is still "Unformed", Lachesis must evaluate childhood vectors and
    # output a permanent hamartia string in her JSON response.
    if (
        state.soul_ledger.hamartia == "Unformed"
        and state.session.epoch_phase == 4
    ):
        msg += (
            "\n\n--- HAMARTIA ASSIGNMENT ---\n"
            "The player's hamartia is currently 'Unformed'. Based on their childhood "
            "soul vectors (metis/bia/kleos/aidos), you MUST now determine their permanent "
            "tragic flaw. Add a field \"assigned_hamartia\" to your JSON response with a "
            "short, evocative hamartia string (e.g., 'Hubris', 'Wrath', 'Vainglory', "
            "'Cowardice'). This will be permanent."
        )

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

    # Oath detection — LLM + regex fallback
    oath_detected = data.get("oath_detected")
    if not oath_detected:
        oath_detected = _detect_oath(action)

    # Oath violation
    oath_violation = data.get("oath_violation")

    return LachesisResponse(
        valid_action=True,
        updated_state=updated,
        vector_deltas=vector_deltas,
        oath_detected=oath_detected,
        oath_violation=oath_violation,
        environment_update=env_update,
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
