"""Hamartia Engine — Deterministic Tragic Flaw Assignment Service.

Assigns the player's permanent hamartia (tragic flaw) based on their
dominant soul vector at Turn 10 (epoch_phase 4). Zero LLM tokens —
pure vector math.

Extracted from Lachesis (P1-002) to isolate deterministic logic
from LLM-dependent judgment. The Kernel is the sole consumer:
it calls determine_hamartia() during Step 2b of _resolve_turn().
"""

from __future__ import annotations

from app.schemas.state import HamartiaProfile, ThreadState


# ---------------------------------------------------------------------------
# Vector → Hamartia Mapping
# ---------------------------------------------------------------------------

VECTOR_HAMARTIA_MAP: dict[str, str] = {
    "metis": "Hubris",       # intellectual overconfidence
    "bia": "Wrath",          # destructive rage
    "kleos": "Vainglory",    # obsessive need for recognition
    "aidos": "Cowardice",    # paralytic fear of action
}

HAMARTIA_PROFILES: dict[str, HamartiaProfile] = {
    "hubris": HamartiaProfile(
        name="Hubris",
        choice_bias="public-risk",
        nemesis_multiplier=1.1,
        eris_bias=0.1,
        style_directive="Tempt the player with public certainty and high-visibility gambles.",
        refusal_pattern="overreach",
        social_cost_bias="public display compounds suspicion",
    ),
    "wrath": HamartiaProfile(
        name="Wrath",
        choice_bias="violent-overreach",
        nemesis_multiplier=1.25,
        eris_bias=0.05,
        style_directive="Violence should feel close, easy, and one choice away.",
        refusal_pattern="violent impulse",
        social_cost_bias="avoidance after aggression reads as weakness and draws reprisals",
    ),
    "vainglory": HamartiaProfile(
        name="Vainglory",
        choice_bias="witness-seeking",
        nemesis_multiplier=1.15,
        eris_bias=0.15,
        style_directive="Offer witness, applause, and public humiliation in equal measure.",
        refusal_pattern="humiliation",
        social_cost_bias="public display compounds suspicion",
    ),
    "cowardice": HamartiaProfile(
        name="Cowardice",
        choice_bias="avoidance",
        nemesis_multiplier=1.0,
        eris_bias=0.2,
        style_directive="Safety should always look one move away, and expensive.",
        refusal_pattern="retreat",
        social_cost_bias="avoidance compounds suspicion and faction heat",
    ),
}


def get_hamartia_profile(hamartia: str) -> HamartiaProfile | None:
    """Return the live profile for a hamartia label."""
    lowered = hamartia.lower()
    for key, profile in HAMARTIA_PROFILES.items():
        if key in lowered:
            return profile.model_copy(deep=True)
    return None


# ---------------------------------------------------------------------------
# Life-Voice (Scribe P3) — discovered at the Fork, deterministic
# ---------------------------------------------------------------------------

_VOICE_BY_FLAW: dict[str, str] = {
    "hubris": (
        "Long, confident clauses that occasionally outrun their footing; the "
        "narrator explains a little too much, certain the reader needs him."
    ),
    "wrath": (
        "Short, percussive sentences. Heat and iron imagery. Anger arrives in "
        "the prose before understanding does."
    ),
    "vainglory": (
        "The narrator performs — aware of an audience, polishing even the "
        "shameful moments until they shine brightest."
    ),
    "cowardice": (
        "Hedged, parenthetical, retreating syntax; the narrator notices every "
        "exit in every room, including the ones in sentences."
    ),
}

_VOICE_GARNISH: dict[str, str] = {
    "metis": "The eye lingers on mechanisms — how things work, how people can be worked.",
    "bia": "The body is always present: weight, grip, the distance to the nearest thing that breaks.",
    "kleos": "Names are repeated like coins counted; being seen matters more than being safe.",
    "aidos": "The telling withholds; the most important things sit just outside the sentences.",
}


def get_life_voice(hamartia: str, state: ThreadState) -> str:
    """Derive the voice this life's book will be written in.

    Deterministic — flaw picks the register, the dominant soul vector adds
    a garnish. Discovered once at the Fork (turn 10), used by the Scribe
    for every chapter, so each incarnation reads like a different author.
    """
    lowered = hamartia.lower()
    base = next(
        (voice for key, voice in _VOICE_BY_FLAW.items() if key in lowered),
        "Plain, weathered, declarative — a life told by someone who survived it.",
    )
    vectors = state.soul_ledger.vectors
    pairs = [
        ("metis", vectors.metis), ("bia", vectors.bia),
        ("kleos", vectors.kleos), ("aidos", vectors.aidos),
    ]
    dominant, _ = max(pairs, key=lambda x: x[1])
    return f"{base} {_VOICE_GARNISH.get(dominant, '')}".strip()


def determine_hamartia(state: ThreadState) -> str | None:
    """Deterministic hamartia assignment based on dominant soul vector.

    Called at Turn 10 (epoch_phase 4) when hamartia is still 'Unformed'.
    Returns the assigned hamartia string, or None if conditions aren't met.

    Conditions (ALL must be true):
        1. state.soul_ledger.hamartia == "Unformed"
        2. state.session.epoch_phase == 4

    This is a pure function with no side effects.
    """
    if state.soul_ledger.hamartia != "Unformed" or state.session.epoch_phase != 4:
        return None

    vectors = state.soul_ledger.vectors
    pairs = [
        ("metis", vectors.metis), ("bia", vectors.bia),
        ("kleos", vectors.kleos), ("aidos", vectors.aidos),
    ]
    dominant_name, _ = max(pairs, key=lambda x: x[1])
    return VECTOR_HAMARTIA_MAP.get(dominant_name, "Aimlessness")
