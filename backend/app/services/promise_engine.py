"""Promise Engine — the ledger's deterministic bookkeeping.

Long-range story structure as an accounting problem: a plant is a typed
debt with a deadline. Small dumb calls bound to a persistent structure
that outlives them — the same trick the factual chronicle plays for
world state, applied to narrative obligation.

Zero LLM tokens. The Re-Outliner PROPOSES ledger changes; only this
module APPLIES them, validating every citation against the constitutional
law (a promise cites a lived turn, never an invented one).
"""

from __future__ import annotations

import logging

from app.schemas.morpheus import (
    MAX_ACTIVE_PROMISES,
    LedgerUpdates,
    Promise,
)
from app.schemas.state import ThreadState

logger = logging.getLogger("nyx.promises")

_ACTIVE = ("planted", "promoted")

# A promise the story failed to pay is a debt fate collects interest on.
ABANDONMENT_OMEN = 0.3


def active_promises(state: ThreadState) -> list[Promise]:
    return [p for p in state.ledger if p.status in _ACTIVE]


def audit_ledger(state: ThreadState, current_turn: int) -> list[str]:
    """Expire promises past their payoff window. Returns audit notes.

    Called once per turn. An abandoned promise is mechanically detectable
    broken structure — the caller may convert each note into omen pressure.
    """
    notes: list[str] = []
    for promise in state.ledger:
        if promise.status in _ACTIVE and current_turn > promise.due_turn:
            promise.status = "abandoned"
            notes.append(
                f"A promise went unpaid: '{promise.description}' "
                f"(planted turn {promise.event_turn}, window closed turn {promise.due_turn})"
            )
            logger.info(f"Promise ABANDONED: {promise.promise_id}")
    return notes


def mark_paid(state: ThreadState, promise_ids: list[str], turn: int) -> list[str]:
    """Mark promises paid (called when an authored beat that pays them plays)."""
    notes: list[str] = []
    wanted = set(promise_ids)
    for promise in state.ledger:
        if promise.promise_id in wanted and promise.status in _ACTIVE:
            promise.status = "paid"
            promise.paid_turn = turn
            notes.append(f"Promise paid: '{promise.description}'")
            logger.info(f"Promise PAID: {promise.promise_id} (turn {turn})")
    return notes


def apply_ledger_updates(
    state: ThreadState,
    updates: LedgerUpdates,
    *,
    based_on_turn: int,
) -> list[str]:
    """Apply the Re-Outliner's proposed changes, constitutionally validated.

    - New plants must cite a lived turn (event_turn <= based_on_turn):
      Morpheus notices what happened; he does not invent a past.
    - Duplicate promise_ids and over-cap plants are dropped with a note.
    - Promotions touch only existing active plants.
    Returns human-readable notes of what was applied/refused.
    """
    notes: list[str] = []
    known_ids = {p.promise_id for p in state.ledger}

    for plant in updates.new_plants:
        if plant.event_turn > based_on_turn:
            notes.append(
                f"REFUSED plant '{plant.promise_id}': cites turn {plant.event_turn} "
                f"beyond the lived record ({based_on_turn}) — the Author may not invent the past"
            )
            logger.warning(notes[-1])
            continue
        if plant.promise_id in known_ids:
            notes.append(f"REFUSED plant '{plant.promise_id}': id already in ledger")
            continue
        if len(active_promises(state)) >= MAX_ACTIVE_PROMISES:
            notes.append(f"REFUSED plant '{plant.promise_id}': ledger at active cap")
            continue
        state.ledger.append(plant.model_copy(deep=True))
        known_ids.add(plant.promise_id)
        notes.append(f"Planted: '{plant.description}' (due turn {plant.due_turn})")
        logger.info(f"Promise PLANTED: {plant.promise_id}")

    for pid in updates.promote_ids:
        promise = next((p for p in state.ledger if p.promise_id == pid), None)
        if promise is None or promise.status != "planted":
            notes.append(f"REFUSED promotion '{pid}': not a planted promise")
            continue
        promise.status = "promoted"
        notes.append(f"Promoted: '{promise.description}'")
        logger.info(f"Promise PROMOTED: {pid}")

    return notes


def render_ledger(state: ThreadState, current_turn: int) -> str:
    """Context block for Clotho / Hypnos: the debts the story carries."""
    promises = active_promises(state)
    if not promises:
        return ""
    lines: list[str] = []
    for p in sorted(promises, key=lambda x: x.due_turn):
        urgency = "DUE NOW" if current_turn >= p.due_turn else f"due by turn {p.due_turn}"
        marker = "PROMOTED" if p.status == "promoted" else "planted"
        why = f" — {p.significance}" if p.significance else ""
        lines.append(f"  • [{marker}, {urgency}] {p.description}{why}")
    return "\n".join(lines)
