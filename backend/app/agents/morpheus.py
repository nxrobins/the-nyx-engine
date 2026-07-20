"""Morpheus — the Re-Outliner. Authors the next epoch from the lived one.

Son of Hypnos, shaper of dreams: he exists only in the gaps. The kernel
fires him at epoch boundaries (behind the dream-curtain) with a FROZEN
snapshot; he returns a BeatSheet or None. He holds no tier in the resolver
hierarchy, mutates nothing, and every beat he writes faces the beat gate.
If he is slow, wrong, or dead, the procedural floor plays and the player
never knows.

Mock mode is deterministic and meaningful: floor directives enriched with
ledger callbacks, plus one plant noticed from the lived record — so the
whole P2 loop (plant → context → payoff window → audit) exercises
hermetically with zero tokens.
"""

from __future__ import annotations

import json
import logging
import re

from app.agents.base import AgentBase, mock_pause
from app.core.config import settings
from app.agents._degrade import note_degraded
from app.schemas.morpheus import (
    AuthoredBeat,
    BeatSheet,
    LedgerUpdates,
    MorpheusSnapshot,
    Promise,
)
from app.services import llm

logger = logging.getLogger("nyx.morpheus")


_SYSTEM = """You are Morpheus, the Re-Outliner of a dark-fantasy life-simulation
engine. A chapter of the player's life just ended. You read what was LIVED and
author the beats of the NEXT chapter so the life acquires the shape of a novel:
promises noticed, planted, and paid.

THE LAW: you may author the future and how things are told — NEVER what
happened. Plants must cite events from the lived record verbatim-faithfully.
The world is physical (mud, iron, wood, flesh, weather); mysticism is rejected
by a machine gate, as is any beat that fails to name a living character.

You receive floor directives (the procedural plan). Elevate them: keep their
structural conventions (NEW SCENE, time skips, NAMES, dialogue, immediate
consequence) and weave in: callbacks to active promises (pay the due ones),
one or two NEW plants noticed from the lived prose, and pressure from the
clocks. Each beat may declare machine-checkable preconditions (npcs_alive,
clocks_unfired) — declare them for any beat that depends on someone or
something; stale beats are dropped silently, so preconditions protect you.

Output ONLY a JSON object:
{
  "beats": [
    {"position": "SETUP"|"COMPLICATION"|"RESOLUTION",
     "directive": "NEW SCENE. ... (50-1200 chars, names a living NPC)",
     "preconditions": {"npcs_alive": [...], "clocks_unfired": [...]},
     "pays_promise_ids": [...]}
  ],
  "ledger_updates": {
    "new_plants": [
      {"promise_id": "p-...", "description": "what was planted, concretely",
       "event_turn": <lived turn it cites>, "significance": "why it will matter",
       "due_turn": <event_turn+3..event_turn+12>, "status": "planted", "paid_turn": 0}
    ],
    "promote_ids": [...]
  }
}"""


def _build_user_prompt(snapshot: MorpheusSnapshot, violations: list[str]) -> str:
    parts = [
        f"THREAD: {snapshot.thread_stamp} — chapter ended at turn {snapshot.boundary_turn}; "
        f"you are authoring turns {snapshot.epoch_start_turn}..{snapshot.epoch_start_turn + 2}.",
        f"SOUL: {snapshot.soul_summary}",
        f"PRESSURES: {snapshot.pressure_summary}",
        f"LIVING NPCs: {', '.join(snapshot.npc_names_alive) or '(none known)'}",
        "CLOCKS: " + ("; ".join(snapshot.clock_lines) or "(none)"),
        "ACTIVE PROMISES:\n" + (
            "\n".join(
                f"  - id={p.promise_id} due_turn={p.due_turn}: {p.description}"
                for p in snapshot.active_promises
            ) or "  (none yet — notice one)"
        ),
        "FACTUAL RECORD:\n" + "\n".join(f"  - {f}" for f in snapshot.factual_chronicle[-6:]),
        "THE LIVED CHAPTER (prose):\n" + "\n---\n".join(snapshot.prose_window[-3:]),
        f"LAST ACTION: {snapshot.last_action}",
        "FLOOR DIRECTIVES TO ELEVATE:\n" + "\n".join(
            f"  [{fb.position} / turn {fb.turn}] {fb.directive}" for fb in snapshot.floor_beats
        ),
    ]
    if violations:
        parts.append(
            "YOUR PREVIOUS ATTEMPT FAILED THE GATE — fix exactly these:\n"
            + "\n".join(f"  - {v}" for v in violations[:10])
        )
    return "\n\n".join(parts)


def _parse_sheet_payload(raw: str) -> dict:
    """Defensive JSON extraction (the Nemesis/Lachesis pattern)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("no JSON object in response")
    return json.loads(cleaned[start:end])


def _assemble_sheet(payload: dict, snapshot: MorpheusSnapshot) -> BeatSheet:
    """Stamp provenance ourselves — the model never authors validity."""
    return BeatSheet(
        sheet_version=1,
        thread_stamp=snapshot.thread_stamp,
        epoch_start_turn=snapshot.epoch_start_turn,
        based_on_turn=snapshot.boundary_turn,
        beats=payload.get("beats", []),
        ledger_updates=payload.get("ledger_updates", {}),
    )


# ---------------------------------------------------------------------------
# Mock — deterministic floor-enrichment, so the loop runs keyless
# ---------------------------------------------------------------------------

def _mock_sheet(snapshot: MorpheusSnapshot) -> BeatSheet:
    npc = snapshot.npc_names_alive[0] if snapshot.npc_names_alive else ""
    ground = f" {npc} carries the memory of it." if npc else ""

    due_promise = next(
        (p for p in snapshot.active_promises
         if p.due_turn <= snapshot.epoch_start_turn + 2),
        None,
    )

    beats: list[AuthoredBeat] = []
    for floor in snapshot.floor_beats:
        directive = floor.directive
        if not directive.lstrip().startswith("NEW SCENE"):
            directive = "NEW SCENE. " + directive
        pays: list[str] = []
        if due_promise and floor.position == "RESOLUTION":
            directive += (
                f"\nTHE LOOM REMEMBERS: pay the promise now — {due_promise.description}. "
                "Its consequence lands in this scene, visibly."
            )
            pays = [due_promise.promise_id]
        elif snapshot.active_promises and floor.position == "SETUP":
            directive += (
                f"\nCALLBACK: let '{snapshot.active_promises[0].description}' "
                "surface in the scene's background, unremarked."
            )
        directive += ground
        beats.append(
            AuthoredBeat(
                position=floor.position,
                directive=directive,
                pays_promise_ids=pays,
            )
        )

    # Notice one plant from the lived record — deterministic, cited.
    action = (snapshot.last_action or "what was done").strip()
    plant = Promise(
        promise_id=f"p-t{snapshot.boundary_turn}",
        description=f"On turn {snapshot.boundary_turn}, the player chose: {action[:200]}",
        event_turn=snapshot.boundary_turn,
        significance="The chapter's last choice will echo.",
        due_turn=min(
            snapshot.boundary_turn + 6, snapshot.boundary_turn + 12
        ),
    )

    return BeatSheet(
        sheet_version=1,
        thread_stamp=snapshot.thread_stamp,
        epoch_start_turn=snapshot.epoch_start_turn,
        based_on_turn=snapshot.boundary_turn,
        beats=beats,
        ledger_updates=LedgerUpdates(new_plants=[plant]),
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Morpheus(AgentBase):
    name = "morpheus"

    async def evaluate(self, state, action: str):  # AgentBase contract stub
        raise NotImplementedError("Morpheus is fired with reoutline(snapshot), never per-turn")

    async def reoutline(self, snapshot: MorpheusSnapshot) -> BeatSheet | None:
        """Author the next epoch. Returns a schema-valid sheet or None.

        The kernel gates each beat (beat_gate) at harvest and re-validates
        preconditions at consumption — this method only guarantees schema
        validity and stamp coherence. None means: the floor plays.
        """
        model = settings.morpheus_model

        if model == "mock":
            await mock_pause(0.3)
            return _mock_sheet(snapshot)

        violations: list[str] = []
        last_exc: Exception | None = None
        for attempt in (1, 2):  # one informed retry
            try:
                raw = await llm.generate(
                    model=model,
                    system_prompt=_SYSTEM,
                    user_message=_build_user_prompt(snapshot, violations),
                    temperature=0.6 if attempt == 1 else 0.8,
                    max_tokens=2000,
                    # Write-behind (the Author works behind the curtain): 2000
                    # tokens cannot land inside the 15s interactive budget.
                    timeout=settings.llm_longform_timeout,
                )
                payload = _parse_sheet_payload(raw)
                sheet = _assemble_sheet(payload, snapshot)
                logger.info(
                    f"Morpheus authored {len(sheet.beats)} beat(s) for "
                    f"epoch starting turn {snapshot.epoch_start_turn} (attempt {attempt})"
                )
                return sheet
            except Exception as exc:
                last_exc = exc
                violations = [f"output invalid: {exc}"]
                logger.warning(f"Morpheus attempt {attempt} failed: {exc!r}")

        if last_exc is not None:
            note_degraded("morpheus", model, last_exc)
        logger.warning("Morpheus: both attempts failed — the floor plays.")
        return None
