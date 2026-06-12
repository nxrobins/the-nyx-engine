"""Assayer tests — the weighing of finished lives."""

from __future__ import annotations

import pytest

from app.core.world_seeds import get_world_seed
from app.schemas.morpheus import Promise
from app.schemas.state import Oath, SessionData, ThreadState
from app.services.assayer import (
    assays_dir,
    compute_verdict,
    list_verdicts,
    world_fitness,
    write_verdict,
)
from app.services.canon import bootstrap_canon
from app.services.doom import begin_doom


def _dead_state(**session_overrides) -> ThreadState:
    session = {
        "player_id": "p", "player_name": "Orin",
        "run_number": 1, "turn_count": 11,
    }
    session.update(session_overrides)
    s = ThreadState(session=SessionData(**session))
    s.world_id = "ashfall"
    s.soul_ledger.hamartia = "Wrath of the Untempered"
    s.canon = bootstrap_canon(get_world_seed("stone"), "Orin", "boy")
    return s


class TestComputeVerdict:
    def test_basic_shape(self):
        v = compute_verdict(_dead_state(), death_reason="The shaft took him.", book_id="b-1")
        assert v.verdict_id == "orin-p-r1-t11"
        assert v.world_id == "ashfall"
        assert v.thread_stamp == "p:1"
        assert v.died_turn == 11
        assert v.epochs_reached == 3
        assert v.book_id == "b-1"
        assert v.clocks_total == 1 and v.clocks_fired == 0

    def test_promise_and_oath_economy(self):
        s = _dead_state()
        s.ledger = [
            Promise(promise_id="p-a", description="The stone he hid in the bedroll", event_turn=3, due_turn=9, status="paid", paid_turn=8),
            Promise(promise_id="p-b", description="The lamp he never returned home", event_turn=4, due_turn=7, status="abandoned"),
            Promise(promise_id="p-c", description="The name he heard in the shaft", event_turn=9, due_turn=14),
        ]
        s.soul_ledger.active_oaths = [
            Oath(oath_id="o1", text="I swear it.", turn_sworn=2, status="fulfilled"),
            Oath(oath_id="o2", text="I vow it.", turn_sworn=5, status="broken"),
        ]
        v = compute_verdict(s, death_reason="x")
        assert (v.promises_planted, v.promises_paid, v.promises_abandoned) == (3, 1, 1)
        assert (v.oaths_sworn, v.oaths_fulfilled, v.oaths_broken) == (2, 1, 1)

    def test_doom_cause_recorded(self):
        s = _dead_state()
        begin_doom(s, cause="broken_oath", description="sworn and betrayed")
        v = compute_verdict(s, death_reason="The oath finished its work.")
        assert v.doom_cause == "broken_oath"

    def test_fired_clock_counted(self):
        s = _dead_state()
        clock = next(iter(s.canon.clocks.values()))
        clock.progress = clock.max_segments
        v = compute_verdict(s, death_reason="x")
        assert v.clocks_fired == 1

    def test_pure_no_mutation(self):
        s = _dead_state()
        before = s.model_dump_json()
        compute_verdict(s, death_reason="x")
        assert s.model_dump_json() == before


class TestShelfOfWeights:
    def test_write_list_roundtrip(self):
        v = compute_verdict(_dead_state(), death_reason="x")
        write_verdict(v)
        shelf = list_verdicts()
        assert len(shelf) == 1 and shelf[0] == v

    def test_bad_verdict_skipped(self):
        write_verdict(compute_verdict(_dead_state(), death_reason="x"))
        (assays_dir() / "broken.verdict.json").write_text("{ nope", encoding="utf-8")
        assert len(list_verdicts()) == 1

    def test_tmp_partials_unlisted(self):
        d = assays_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "half.tmp").write_text("{", encoding="utf-8")
        assert list_verdicts() == []


class TestFitness:
    def _verdict(self, *, run: int, died: int, fired: int = 0, paid: int = 0,
                 planted: int = 0, doom: str = "") -> None:
        s = _dead_state(turn_count=died, run_number=run)
        if fired:
            clock = next(iter(s.canon.clocks.values()))
            clock.progress = clock.max_segments
        s.ledger = [
            Promise(
                promise_id=f"p-{i}", description="A debt the story still remembers",
                event_turn=1, due_turn=10,
                status="paid" if i < paid else "planted",
            )
            for i in range(planted)
        ]
        if doom:
            begin_doom(s, cause=doom, description="x")
        write_verdict(compute_verdict(s, death_reason="x"))

    def test_aggregation(self):
        self._verdict(run=1, died=12, fired=1, planted=2, paid=2, doom="broken_oath")
        self._verdict(run=2, died=6)
        report = world_fitness()
        assert "ashfall" in report
        record = report["ashfall"]
        assert record["lives"] == 2
        assert record["avg_died_turn"] == 9.0
        assert record["clock_fire_rate"] == 0.5
        assert record["promise_pay_rate"] == 1.0
        assert record["death_causes"] == {"broken_oath": 1, "no_doom": 1}
        assert 0.0 < record["vitality"] <= 10.0

    def test_world_filter(self):
        self._verdict(run=1, died=12)
        assert world_fitness("ashfall")["ashfall"]["lives"] == 1
        assert world_fitness("thornwell") == {}

    def test_empty_shelf_empty_report(self):
        assert world_fitness() == {}
