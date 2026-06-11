"""Scene clock + intervention disposition tests — the world acts back."""

from __future__ import annotations

import pytest

from app.core.world_seeds import get_world_seed
from app.schemas.state import SceneClock, ThreadState
from app.services.canon import (
    advance_clock,
    apply_intervention_dispositions,
    bootstrap_canon,
    tick_scene_clocks,
)


@pytest.fixture
def state() -> ThreadState:
    s = ThreadState()
    s.canon = bootstrap_canon(get_world_seed("stone"), "Hero", "boy")
    return s


def _the_clock(state: ThreadState) -> SceneClock:
    return next(iter(state.canon.clocks.values()))


class TestAdvanceClock:
    def test_advances_and_reports_fire(self, state):
        clock = _the_clock(state)
        clock.progress = clock.max_segments - 1
        fired = advance_clock(state, clock.clock_id, 1)
        assert fired is clock
        assert clock.progress == clock.max_segments

    def test_partial_advance_returns_none(self, state):
        clock = _the_clock(state)
        assert advance_clock(state, clock.clock_id, 1) is None
        assert clock.progress == 1

    def test_already_fired_clock_is_inert(self, state):
        clock = _the_clock(state)
        clock.progress = clock.max_segments
        assert advance_clock(state, clock.clock_id, 1) is None
        assert clock.progress == clock.max_segments

    def test_unknown_clock_returns_none(self, state):
        assert advance_clock(state, "clock_nonexistent", 1) is None


class TestTickPolicy:
    def test_quiet_turn_does_not_tick(self, state):
        result = tick_scene_clocks(
            state, intervention_struck=False, resolution_beat=False
        )
        assert not result.fired
        assert _the_clock(state).progress == 0

    def test_intervention_ticks_one(self, state):
        tick_scene_clocks(state, intervention_struck=True, resolution_beat=False)
        assert _the_clock(state).progress == 1

    def test_resolution_beat_ticks_one(self, state):
        tick_scene_clocks(state, intervention_struck=False, resolution_beat=True)
        assert _the_clock(state).progress == 1

    def test_coasting_ticks_one(self, state):
        state.pressures.stability_streak = 3
        tick_scene_clocks(state, intervention_struck=False, resolution_beat=False)
        assert _the_clock(state).progress == 1

    def test_advance_caps_at_two(self, state):
        state.pressures.stability_streak = 5
        tick_scene_clocks(state, intervention_struck=True, resolution_beat=True)
        assert _the_clock(state).progress == 2

    def test_fired_clock_becomes_scene_truth(self, state):
        clock = _the_clock(state)
        clock.progress = clock.max_segments - 1
        result = tick_scene_clocks(
            state, intervention_struck=True, resolution_beat=False
        )
        assert result.fired == [clock]
        assert result.notes and clock.stakes in result.notes[0]
        assert result.pressure_spike.get("omen", 0) > 0
        scene = state.canon.current_scene
        assert clock.clock_id not in scene.active_clock_ids
        assert clock.stakes in scene.carryover_consequence

    def test_no_canon_is_safe(self):
        bare = ThreadState()
        result = tick_scene_clocks(
            bare, intervention_struck=True, resolution_beat=True
        )
        assert not result.fired and not result.notes


class TestInterventionDispositions:
    def test_nemesis_strike_marks_witnesses(self, state):
        npc = next(iter(state.canon.npcs.values()))
        trust_before, fear_before = npc.trust, npc.fear
        note = apply_intervention_dispositions(state, kind="nemesis")
        assert npc.trust < trust_before
        assert npc.fear > fear_before
        assert npc.name in note

    def test_oath_break_costs_most_trust(self, state):
        npc = next(iter(state.canon.npcs.values()))
        trust_before = npc.trust
        apply_intervention_dispositions(state, kind="oath_broken")
        assert npc.trust == pytest.approx(trust_before - 1.0)

    def test_oath_break_hardens_factions(self, state):
        faction = next(iter(state.canon.factions.values()))
        hostility_before = faction.hostility
        apply_intervention_dispositions(state, kind="oath_broken")
        assert faction.hostility > hostility_before

    def test_eris_scales_with_severity(self, state):
        npc = next(iter(state.canon.npcs.values()))
        fear_before = npc.fear
        apply_intervention_dispositions(state, kind="eris", severity=0.5)
        assert npc.fear == pytest.approx(fear_before + 0.15)

    def test_dead_npcs_do_not_react(self, state):
        for npc in state.canon.npcs.values():
            npc.status = "dead"
        note = apply_intervention_dispositions(state, kind="nemesis")
        assert note == ""

    def test_unknown_kind_is_noop(self, state):
        assert apply_intervention_dispositions(state, kind="hermes") == ""

    def test_no_canon_is_safe(self):
        bare = ThreadState()
        assert apply_intervention_dispositions(bare, kind="nemesis") == ""
