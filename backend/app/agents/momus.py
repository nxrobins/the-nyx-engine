"""Momus - The Validator / Literary Law Enforcer v3.1 (Sprint 9: The Voice).

Two categories of validation:

1. **Hallucinations** — factual contradictions against thread state:
   environment terrain, oath references, death language.
   These set `valid=False` and are logged as warnings.

2. **Law Violations** — breaches of the Laws of the Loom:
   Law I   (Show Then Tell) — excessive emotion naming (threshold: 3)
   Law II  (Player Acts) — excessive passive voice (threshold: 6)
   Law IV  (No Anachronisms) — anachronisms
   Law VI  (Economy) — paragraph overflow
   These are tracked in `law_violations` for observability
   but do NOT set `valid=False` (style, not state).

All checks are deterministic. No LLM calls.
Phase 3 will add spaCy NER pipeline for entity tracking.
"""

from __future__ import annotations

import asyncio
import re

from app.agents.base import AgentBase
from app.schemas.state import MomusValidation, ThreadState

# ---------------------------------------------------------------------------
# Static rule tables
# ---------------------------------------------------------------------------

_TERRAIN_PAIRS: list[tuple[str, str]] = [
    ("ocean", "desert"), ("sea", "desert"), ("forest", "ocean"),
    ("mountain", "underwater"), ("cave", "sky"), ("dungeon", "meadow"),
]

# Law IV — The Ancient Guardrail: modern technology & concepts
_ANACHRONISMS: set[str] = {
    # communication
    "phone", "telephone", "cellphone", "smartphone", "email",
    "internet", "wifi", "website", "computer", "laptop", "tablet",
    "radio", "television", "tv", "broadcast",
    # transport
    "car", "automobile", "truck", "bus", "train", "railroad",
    "airplane", "helicopter", "jet", "subway", "motorcycle",
    # weapons (post-gunpowder)
    "gun", "pistol", "rifle", "bullet", "bomb", "grenade",
    "cannon", "missile", "rocket", "dynamite", "explosive",
    # power & materials
    "electricity", "battery", "generator", "motor", "engine",
    "plastic", "nylon", "concrete", "asphalt", "semiconductor",
    # industry
    "factory", "skyscraper", "elevator", "escalator",
    "robot", "machine", "microchip", "software", "hardware",
    # media
    "photograph", "camera", "video", "film", "cinema",
    "newspaper", "magazine",
    # timekeeping (mechanical)
    "clock", "wristwatch",
    # optics
    "glasses", "spectacles", "binoculars", "telescope", "microscope",
    # political systems (modern)
    "democracy", "communism", "capitalism", "socialism",
}

# Law I — Show Then Tell: named emotions
_EMOTION_THRESHOLD = 3  # allow up to 3 instances (show-then-tell permits naming after physical evidence)

_EMOTION_WORDS: list[str] = [
    "afraid", "angry", "anxious", "ashamed", "bitter",
    "cheerful", "confused", "content", "delighted", "depressed",
    "desperate", "disappointed", "disgusted", "embarrassed", "envious",
    "excited", "frightened", "frustrated", "furious", "grateful",
    "guilty", "happy", "heartbroken", "hopeful", "hopeless",
    "horrified", "humiliated", "impatient", "irritated", "jealous",
    "joyful", "lonely", "melancholy", "miserable", "nervous",
    "nostalgic", "overjoyed", "panicked", "peaceful", "proud",
    "regretful", "relieved", "resentful", "sad", "satisfied",
    "scared", "shocked", "sorrowful", "surprised", "terrified",
    "thrilled", "tormented", "troubled", "uneasy", "worried",
]

_EMOTION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:felt|feeling|feels|was|were|is|are|seemed|appeared|looked|became|grew)\s+"
    + r"(?:" + "|".join(re.escape(e) for e in _EMOTION_WORDS) + r")\b",
    re.IGNORECASE,
)

# Law II — The Player Acts: passive "to be" verbs
_PASSIVE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:was|were|is|are|been)\b", re.IGNORECASE,
)
_PASSIVE_THRESHOLD = 6  # raised from 3; new law allows "was/were" when player is subject

# Law VI — Economy of Breath: max paragraphs per turn
_PARAGRAPH_LIMIT = 5  # generous threshold (Laws say 2-3, allow some margin)


class Momus(AgentBase):
    name = "momus"

    async def evaluate(
        self, state: ThreadState, action: str
    ) -> MomusValidation:
        # Momus doesn't use `action` — it validates prose, not input.
        # This signature satisfies the base class; prose is passed via
        # validate_prose(). For now, always passes in evaluate().
        await asyncio.sleep(0.05)
        return MomusValidation(valid=True)

    async def validate_prose(
        self, prose: str, state: ThreadState
    ) -> MomusValidation:
        """Check Clotho's prose for state hallucinations and Literary Law violations."""
        await asyncio.sleep(0.1)

        hallucinations: list[str] = []
        law_violations: list[str] = []
        prose_lower = prose.lower()

        # ── STATE HALLUCINATION CHECKS ────────────────────────────────

        # Check 1: Environment consistency
        env_lower = state.session.current_environment.lower()
        for a, b in _TERRAIN_PAIRS:
            if a in env_lower and b in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{b}' but environment is '{a}'-related."
                )
            elif b in env_lower and a in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{a}' but environment is '{b}'-related."
                )

        # Check 2: Oath references without active oaths
        if re.search(r"\b(oath|sworn|vow|promise)\b", prose_lower):
            if not state.soul_ledger.active_oaths:
                hallucinations.append(
                    "Prose references oaths/vows but no active oaths in state."
                )

        # Check 3: Death language when soul is healthy
        death_words = re.findall(
            r"\b(you die|you are dead|your life ends|you perish)\b", prose_lower
        )
        if death_words:
            vals = list(state.soul_ledger.vectors.model_dump().values())
            if any(v > 3.0 for v in vals):
                hallucinations.append(
                    "Prose declares player death but soul vectors are not collapsed."
                )

        # ── LITERARY LAW CHECKS ───────────────────────────────────────

        # Law IV — The Ancient Guardrail: anachronism detection
        found_anachronisms = _detect_anachronisms(prose_lower)
        if found_anachronisms:
            law_violations.append(
                f"Law IV (Ancient Guardrail): anachronism detected — "
                f"{', '.join(sorted(found_anachronisms))}."
            )

        # Law I — Show Then Tell: named emotions (threshold-based)
        emotion_matches = _EMOTION_PATTERN.findall(prose)
        if len(emotion_matches) > _EMOTION_THRESHOLD:
            law_violations.append(
                f"Law I (Show Then Tell): excessive emotion naming — "
                f"found {len(emotion_matches)} instance(s) (threshold: {_EMOTION_THRESHOLD})."
            )

        # Law II — The Player Acts: passive voice
        passive_count = len(_PASSIVE_PATTERN.findall(prose))
        if passive_count > _PASSIVE_THRESHOLD:
            law_violations.append(
                f"Law II (Player Acts): {passive_count} passive 'to be' "
                f"verbs (threshold: {_PASSIVE_THRESHOLD})."
            )

        # Law VI — Economy of Breath: paragraph count
        paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
        if len(paragraphs) > _PARAGRAPH_LIMIT:
            law_violations.append(
                f"Law VI (Economy of Breath): {len(paragraphs)} paragraphs "
                f"(limit: {_PARAGRAPH_LIMIT})."
            )

        return MomusValidation(
            valid=len(hallucinations) == 0,
            hallucinations=hallucinations,
            law_violations=law_violations,
            corrected_prose=prose,  # Phase 3: actually correct it
        )


def _detect_anachronisms(prose_lower: str) -> set[str]:
    """Return set of anachronistic words found in the prose."""
    found: set[str] = set()
    for word in _ANACHRONISMS:
        # Word-boundary match to avoid substring false positives
        # e.g. "bus" shouldn't match inside "ambush"
        if re.search(rf"\b{re.escape(word)}\b", prose_lower):
            found.add(word)
    return found
