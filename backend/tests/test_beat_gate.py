"""Beat Gate tests — Momus mocks the Author too."""

from __future__ import annotations

import pytest

from app.core.world_seeds import get_world_seed
from app.schemas.morpheus import AuthoredBeat, BeatPrecondition
from app.schemas.state import ThreadState
from app.services.beat_gate import gate_beat, preconditions_hold
from app.services.canon import bootstrap_canon


@pytest.fixture
def state() -> ThreadState:
    s = ThreadState()
    s.canon = bootstrap_canon(get_world_seed("stone"), "Hero", "boy")  # Maren, Kael
    return s


def _beat(directive: str, **pre) -> AuthoredBeat:
    return AuthoredBeat(
        position="SETUP",
        directive=directive,
        preconditions=BeatPrecondition(**pre),
    )


_GOOD = (
    "NEW SCENE. Time has passed. Maren is mending sacks by the lamp when the "
    "knock comes — two men from the Authority, asking for Kael by name."
)


class TestGateBeat:
    def test_grounded_beat_passes(self, state):
        assert gate_beat(_beat(_GOOD), state) == []

    def test_missing_new_scene_rejected(self, state):
        bad = _beat("Maren waits by the lamp for the knock that is coming to the door tonight.")
        assert any("NEW SCENE" in v for v in gate_beat(bad, state))

    def test_mysticism_rejected(self, state):
        bad = _beat(
            "NEW SCENE. Maren stares as the fabric of reality shivers above the "
            "lamp and a threshold between worlds breathes open."
        )
        violations = gate_beat(bad, state)
        assert any("mysticism" in v for v in violations)

    def test_unnamed_beat_rejected(self, state):
        bad = _beat(
            "NEW SCENE. Someone is at home doing something domestic when a "
            "disruption arrives and tension fills the little room."
        )
        assert any("no living canon NPC" in v for v in gate_beat(bad, state))

    def test_unknown_precondition_npc_rejected(self, state):
        bad = _beat(_GOOD, npcs_alive=["Bryd"])  # Bryd is Thornwell, not Ashfall
        assert any("unknown NPC" in v for v in gate_beat(bad, state))

    def test_unknown_precondition_clock_rejected(self, state):
        bad = _beat(_GOOD, clocks_unfired=["clock_nonexistent"])
        assert any("unknown clock" in v for v in gate_beat(bad, state))

    def test_dead_npc_name_still_grounds_but_liveness_is_consume_time(self, state):
        # Kael dies: a directive naming only Kael fails the named-grounding
        # check (he is no longer a LIVING name to ground against).
        for npc in state.canon.npcs.values():
            if npc.name == "Kael":
                npc.status = "dead"
        bad = _beat(
            "NEW SCENE. Kael hammers the brace while the lamp gutters and the "
            "shaft breathes cold on the back of his neck."
        )
        assert any("no living canon NPC" in v for v in gate_beat(bad, state))


class TestPreconditionsHold:
    def test_alive_npc_holds(self, state):
        assert preconditions_hold(_beat(_GOOD, npcs_alive=["Maren"]), state)

    def test_dead_npc_fails(self, state):
        beat = _beat(_GOOD, npcs_alive=["Maren"])
        for npc in state.canon.npcs.values():
            if npc.name == "Maren":
                npc.status = "dead"
        assert not preconditions_hold(beat, state)

    def test_unfired_clock_holds_fired_fails(self, state):
        clock_id = next(iter(state.canon.clocks))
        beat = _beat(_GOOD, clocks_unfired=[clock_id])
        assert preconditions_hold(beat, state)
        state.canon.clocks[clock_id].progress = state.canon.clocks[clock_id].max_segments
        assert not preconditions_hold(beat, state)

    def test_no_canon_only_unconditional_beats_hold(self):
        bare = ThreadState()
        assert preconditions_hold(_beat(_GOOD), bare)
        assert not preconditions_hold(_beat(_GOOD, npcs_alive=["Maren"]), bare)
