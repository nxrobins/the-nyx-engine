"""Scribe Gate — the deterministic screen every drafted chapter must pass.

The same posture as the beat gate: Momus mocks the Author's biographer
too. A chapter is retrospective prose, so it cannot be checked against
the live scene — but it CAN be checked against the things that never
change: the world has no anachronisms, waking reality is physical, and
a biography that names nobody from the life it narrates is a fraud.

Zero LLM tokens. A failing chapter simply does not exist; the book has
one fewer chapter and the game never notices.
"""

from __future__ import annotations

from app.agents.momus import _detect_anachronisms  # shared in-repo law, deliberately
from app.schemas.book import MAX_CHAPTER_CHARS, ScribeSnapshot
from app.services.beat_gate import MYSTICISM_BANNED

_MIN_CHAPTER_CHARS = 100


def gate_chapter(prose: str, snapshot: ScribeSnapshot) -> list[str]:
    """Returns violations; empty list = the chapter may enter the book."""
    violations: list[str] = []
    lowered = prose.lower()

    if not _MIN_CHAPTER_CHARS <= len(prose) <= MAX_CHAPTER_CHARS:
        violations.append(
            f"length {len(prose)} outside {_MIN_CHAPTER_CHARS}..{MAX_CHAPTER_CHARS}"
        )

    # Law IV — the Age of Ash has no telephones, in prose or in memoir.
    anachronisms = _detect_anachronisms(lowered)
    if anachronisms:
        violations.append(f"anachronisms: {sorted(anachronisms)}")

    # Law VII — waking reality is physical, even retold. (The final chapter
    # may narrate the doom, but never as reality-bending.)
    for term in MYSTICISM_BANNED:
        if term in lowered:
            violations.append(f"mysticism: '{term}' forbidden in a chapter")

    # A biography that names nobody from the life is a fraud: the chapter
    # must mention the settlement or at least one known canon name.
    grounding_names = [n for n in snapshot.npc_names if n]
    if snapshot.settlement:
        grounding_names.append(snapshot.settlement)
    if grounding_names and not any(name in prose for name in grounding_names):
        violations.append(
            f"chapter names nobody from the life (known: {grounding_names[:6]})"
        )

    return violations
