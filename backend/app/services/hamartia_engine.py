"""Hamartia Engine — Deterministic Tragic Flaw Assignment Service.

Assigns the player's permanent hamartia (tragic flaw) based on their
dominant soul vector at Turn 10 (epoch_phase 4). Zero LLM tokens —
pure vector math.

Extracted from Lachesis (P1-002) to isolate deterministic logic
from LLM-dependent judgment. The Kernel is the sole consumer:
it calls determine_hamartia() during Step 2b of _resolve_turn().
"""

from __future__ import annotations

from app.schemas.state import ThreadState


# ---------------------------------------------------------------------------
# Vector → Hamartia Mapping
# ---------------------------------------------------------------------------

VECTOR_HAMARTIA_MAP: dict[str, str] = {
    "metis": "Hubris",       # intellectual overconfidence
    "bia": "Wrath",          # destructive rage
    "kleos": "Vainglory",    # obsessive need for recognition
    "aidos": "Cowardice",    # paralytic fear of action
}


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
