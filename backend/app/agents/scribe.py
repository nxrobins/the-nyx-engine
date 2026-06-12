"""The Scribe — write-behind biographer of the thread.

While the player lives forward, the Scribe writes backward: each epoch,
once lived, is drafted as a chapter in the life-voice discovered at the
Fork. At death the chapters are already waiting — the book lands minutes
after the thread severs because it was being written all along.

Constitutional ground: the Scribe retells, never retcons. Its raw
material is the lived prose and the factual chronicle; its output faces
the scribe gate; a failed draft means a missing chapter, never a wrong one.

Mock mode is deterministic and real: a faithful condensation of the
lived prose under an epoch heading, voice-stamped — so the entire
chapters→book→library loop exercises hermetically at zero tokens.
"""

from __future__ import annotations

import logging

from app.agents.base import AgentBase, mock_pause
from app.core.config import settings
from app.schemas.book import Chapter, ScribeSnapshot
from app.services import llm
from app.services.scribe_gate import gate_chapter

logger = logging.getLogger("nyx.scribe")


_SYSTEM = """You are the Scribe of a dark-fantasy life-engine. A chapter of a
mortal's life has just been lived — you write it into their book.

THE LAW: you retell, you never retcon. Every event in your chapter must be
faithful to the lived prose and the factual record. You may compress, reorder
emphasis, and shape the telling — you may not change what happened, who lived,
who died, or what was said.

Write in THIRD person past tense, in the LIFE-VOICE provided — this book
should read like it was written by one particular author shaped by this
particular flaw. The world is physical (mud, iron, wood, flesh, weather);
no mysticism, no anachronisms. Name the people and the places: a biography
that names nobody is a fraud and will be rejected by a machine gate.

If a death is provided, this is the FINAL chapter: narrate the ending the
record gives you, land the epitaph as the closing line, and do not soften it.

Output ONLY the chapter prose — no title, no headers, no commentary.
600-1400 words."""


def _build_user_prompt(snapshot: ScribeSnapshot, violations: list[str]) -> str:
    parts = [
        f"SUBJECT: {snapshot.player_name}, hamartia {snapshot.hamartia or 'unformed'}, "
        f"of {snapshot.settlement or 'no fixed place'}.",
        f"CHAPTER: {snapshot.epoch_index} — {snapshot.epoch_name} "
        f"(turns {snapshot.covers_turns[0]}..{snapshot.covers_turns[1]}, "
        f"age ~{snapshot.player_age}).",
        f"LIFE-VOICE (write in exactly this register): {snapshot.life_voice or 'plain and weathered'}",
        "PEOPLE OF THE LIFE: " + (", ".join(snapshot.npc_names) or "(unnamed)"),
        "FACTUAL RECORD (must not be contradicted):\n"
        + ("\n".join(f"  - {f}" for f in snapshot.factual_chronicle) or "  (none yet)"),
        "MYTHIC CHRONICLE:\n"
        + ("\n".join(f"  - {c}" for c in snapshot.chronicle) or "  (none yet)"),
        "THE LIVED PROSE (your raw material):\n" + "\n---\n".join(snapshot.prose_window),
    ]
    if snapshot.death_reason:
        parts.append(
            f"THE DEATH (this is the final chapter): {snapshot.death_reason}\n"
            f"EPITAPH (close with it): {snapshot.epitaph}"
        )
    if violations:
        parts.append(
            "YOUR PREVIOUS DRAFT FAILED THE GATE — fix exactly these:\n"
            + "\n".join(f"  - {v}" for v in violations[:8])
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Mock — a faithful deterministic condensation
# ---------------------------------------------------------------------------

def _mock_prose(snapshot: ScribeSnapshot) -> str:
    name = snapshot.player_name
    place = f" in {snapshot.settlement}" if snapshot.settlement else ""
    opening = (
        f"In the years the record calls turns {snapshot.covers_turns[0]} to "
        f"{snapshot.covers_turns[1]}, {name} lived{place} the chapter later "
        f"named {snapshot.epoch_name}."
    )
    lived = " ".join(p.strip() for p in snapshot.prose_window if p.strip())
    facts = ""
    if snapshot.factual_chronicle:
        facts = " The record holds: " + " ".join(snapshot.factual_chronicle[-2:])
    voice_stamp = f" ({snapshot.life_voice})" if snapshot.life_voice else ""

    body = f"{opening}{voice_stamp}\n\n{lived}{facts}"

    if snapshot.death_reason:
        body += (
            f"\n\nAnd there the thread ended: {snapshot.death_reason} "
            f"The stone above the grave says only: {snapshot.epitaph}"
        )

    # Respect the chapter ceiling deterministically.
    return body[:7800]


def _mock_title(snapshot: ScribeSnapshot) -> str:
    if snapshot.death_reason:
        return f"Chapter {snapshot.epoch_index}: The Severing"
    return f"Chapter {snapshot.epoch_index}: {snapshot.epoch_name}"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Scribe(AgentBase):
    name = "scribe"

    async def evaluate(self, state, action: str):  # AgentBase contract stub
        raise NotImplementedError("The Scribe is fired with draft_chapter(snapshot)")

    async def draft_chapter(self, snapshot: ScribeSnapshot) -> Chapter | None:
        """Draft one lived epoch as a chapter. None = the book has one fewer.

        Every draft (mock or real) faces the scribe gate; only passing
        prose becomes a Chapter.
        """
        model = settings.scribe_model

        if model == "mock":
            await mock_pause(0.3)
            prose = _mock_prose(snapshot)
            violations = gate_chapter(prose, snapshot)
            if violations:
                logger.warning(f"Scribe mock draft failed the gate: {violations}")
                return None
            return Chapter(
                epoch_index=snapshot.epoch_index,
                title=_mock_title(snapshot),
                covers_turns=snapshot.covers_turns,
                prose=prose,
                thread_stamp=snapshot.thread_stamp,
                based_on_turn=snapshot.boundary_turn,
            )

        violations: list[str] = []
        for attempt in (1, 2):  # one informed retry
            try:
                prose = await llm.generate(
                    model=model,
                    system_prompt=_SYSTEM,
                    user_message=_build_user_prompt(snapshot, violations),
                    temperature=0.7,
                    max_tokens=2200,
                )
                prose = prose.strip()
                violations = gate_chapter(prose, snapshot)
                if violations:
                    logger.warning(
                        f"Scribe attempt {attempt} failed the gate: {violations}"
                    )
                    continue
                logger.info(
                    f"Scribe drafted chapter {snapshot.epoch_index} "
                    f"({len(prose)} chars, attempt {attempt})"
                )
                return Chapter(
                    epoch_index=snapshot.epoch_index,
                    title=_mock_title(snapshot),
                    covers_turns=snapshot.covers_turns,
                    prose=prose,
                    thread_stamp=snapshot.thread_stamp,
                    based_on_turn=snapshot.boundary_turn,
                )
            except Exception as exc:
                violations = [f"draft failed: {exc}"]
                logger.warning(f"Scribe attempt {attempt} error: {exc!r}")

        logger.warning(
            f"Scribe: chapter {snapshot.epoch_index} unwritten — the book is shorter."
        )
        return None
