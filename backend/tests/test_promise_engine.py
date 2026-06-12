"""Promise Engine tests — the ledger's constitutional bookkeeping."""

from __future__ import annotations

import pytest

from app.schemas.morpheus import LedgerUpdates, Promise
from app.schemas.state import ThreadState
from app.services.promise_engine import (
    active_promises,
    apply_ledger_updates,
    audit_ledger,
    mark_paid,
    render_ledger,
)


def _promise(pid="p-stone", event=3, due=9, status="planted", **kw) -> Promise:
    return Promise(
        promise_id=pid,
        description=kw.pop("description", "Kai pocketed the black stone from the shaft"),
        event_turn=event,
        due_turn=due,
        status=status,
        **kw,
    )


@pytest.fixture
def state() -> ThreadState:
    return ThreadState()


class TestAudit:
    def test_past_due_promise_abandons(self, state):
        state.ledger.append(_promise(due=5))
        notes = audit_ledger(state, current_turn=6)
        assert state.ledger[0].status == "abandoned"
        assert len(notes) == 1 and "unpaid" in notes[0]

    def test_open_window_untouched(self, state):
        state.ledger.append(_promise(due=9))
        assert audit_ledger(state, current_turn=9) == []
        assert state.ledger[0].status == "planted"

    def test_paid_promise_never_abandons(self, state):
        state.ledger.append(_promise(due=5, status="paid"))
        assert audit_ledger(state, current_turn=20) == []
        assert state.ledger[0].status == "paid"


class TestApplyUpdates:
    def test_valid_plant_lands(self, state):
        updates = LedgerUpdates(new_plants=[_promise()])
        notes = apply_ledger_updates(state, updates, based_on_turn=3)
        assert len(active_promises(state)) == 1
        assert any("Planted" in n for n in notes)

    def test_future_citation_refused(self, state):
        # The Author may not invent the past: event_turn beyond the record.
        updates = LedgerUpdates(new_plants=[_promise(event=7, due=12)])
        notes = apply_ledger_updates(state, updates, based_on_turn=3)
        assert state.ledger == []
        assert any("may not invent the past" in n for n in notes)

    def test_duplicate_id_refused(self, state):
        state.ledger.append(_promise())
        updates = LedgerUpdates(new_plants=[_promise()])
        notes = apply_ledger_updates(state, updates, based_on_turn=5)
        assert len(state.ledger) == 1
        assert any("already in ledger" in n for n in notes)

    def test_active_cap_enforced(self, state):
        for i in range(10):
            state.ledger.append(_promise(pid=f"p-{i}", event=1, due=12))
        updates = LedgerUpdates(new_plants=[_promise(pid="p-over")])
        apply_ledger_updates(state, updates, based_on_turn=5)
        assert all(p.promise_id != "p-over" for p in state.ledger)

    def test_promotion_of_planted(self, state):
        state.ledger.append(_promise())
        apply_ledger_updates(
            state, LedgerUpdates(promote_ids=["p-stone"]), based_on_turn=5
        )
        assert state.ledger[0].status == "promoted"

    def test_promotion_of_unknown_refused(self, state):
        notes = apply_ledger_updates(
            state, LedgerUpdates(promote_ids=["p-ghost"]), based_on_turn=5
        )
        assert any("REFUSED promotion" in n for n in notes)


class TestPayment:
    def test_mark_paid(self, state):
        state.ledger.append(_promise())
        notes = mark_paid(state, ["p-stone"], turn=7)
        assert state.ledger[0].status == "paid"
        assert state.ledger[0].paid_turn == 7
        assert len(notes) == 1

    def test_paying_abandoned_is_noop(self, state):
        state.ledger.append(_promise(status="abandoned"))
        assert mark_paid(state, ["p-stone"], turn=7) == []
        assert state.ledger[0].status == "abandoned"


class TestRender:
    def test_empty_ledger_renders_empty(self, state):
        assert render_ledger(state, current_turn=4) == ""

    def test_renders_urgency_and_promotion(self, state):
        state.ledger.append(_promise(due=4, status="promoted"))
        out = render_ledger(state, current_turn=4)
        assert "DUE NOW" in out and "PROMOTED" in out
        assert "black stone" in out

    def test_paid_and_abandoned_not_rendered(self, state):
        state.ledger.append(_promise(pid="p-a", status="paid"))
        state.ledger.append(_promise(pid="p-b", status="abandoned"))
        assert render_ledger(state, current_turn=5) == ""
