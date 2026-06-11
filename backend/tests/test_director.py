"""Adult Director tests — procedural beats for turn 10+."""

from __future__ import annotations

import pytest

from app.core.director import ADULT_CADENCE, select_adult_beat
from app.core.world_seeds import get_world_seed
from app.schemas.state import Oath, OathTerms, ThreadState
from app.services.canon import bootstrap_canon
from app.services.doom import begin_doom
from app.services.hamartia_engine import get_hamartia_profile


@pytest.fixture
def state() -> ThreadState:
    s = ThreadState()
    s.canon = bootstrap_canon(get_world_seed("light"), "Hero", "girl")
    return s


class TestCadence:
    def test_three_turn_chapter_cycle(self, state):
        positions = [select_adult_beat(state, t)[0] for t in (10, 11, 12, 13, 14, 15)]
        assert positions == list(ADULT_CADENCE) * 2

    def test_every_beat_isolates_the_scene(self, state):
        for turn in (10, 11, 12):
            _, directive = select_adult_beat(state, turn)
            assert directive.startswith("NEW SCENE.")

    def test_deterministic(self, state):
        assert select_adult_beat(state, 11) == select_adult_beat(state, 11)


class TestDriverPriority:
    def test_doom_outranks_everything(self, state):
        begin_doom(state, cause="broken_oath", description="The oath broke.")
        state.pressures.suspicion = 5.0
        _, directive = select_adult_beat(state, 10)
        assert "DOOM" in directive

    def test_maturing_clock_outranks_oath_and_pressure(self, state):
        clock = next(iter(state.canon.clocks.values()))
        clock.progress = clock.max_segments - 1
        state.pressures.suspicion = 5.0
        state.soul_ledger.active_oaths.append(
            Oath(oath_id="o1", text="I swear it.", turn_sworn=2)
        )
        _, directive = select_adult_beat(state, 10)
        assert "THE CLOCK" in directive
        assert clock.label in directive

    def test_unripe_clock_does_not_drive(self, state):
        clock = next(iter(state.canon.clocks.values()))
        clock.progress = 0
        _, directive = select_adult_beat(state, 10)
        assert "THE CLOCK" not in directive

    def test_active_oath_drives_when_no_doom_or_clock(self, state):
        state.soul_ledger.active_oaths.append(
            Oath(
                oath_id="o1",
                text="I swear to repay Torval.",
                turn_sworn=2,
                terms=OathTerms(promised_action="repay Torval", price="ten silver"),
            )
        )
        _, directive = select_adult_beat(state, 10)
        assert "THE OATH" in directive
        assert "I swear to repay Torval." in directive
        assert "ten silver" in directive

    def test_fulfilled_oath_does_not_drive(self, state):
        state.soul_ledger.active_oaths.append(
            Oath(oath_id="o1", text="Done.", turn_sworn=2, status="fulfilled")
        )
        _, directive = select_adult_beat(state, 10)
        assert "THE OATH" not in directive

    def test_loudest_pressure_drives(self, state):
        state.pressures.suspicion = 3.0
        state.pressures.scarcity = 1.0
        _, directive = select_adult_beat(state, 10)
        assert "SUSPICION" in directive
        assert "3.0" in directive

    def test_quiet_pressures_fall_through(self, state):
        state.pressures.suspicion = 1.0
        _, directive = select_adult_beat(state, 10)
        assert "SUSPICION" not in directive

    def test_hamartia_tempts_on_even_chapters(self, state):
        state.soul_ledger.hamartia_profile = get_hamartia_profile("Wrath")
        _, directive = select_adult_beat(state, 10)  # chapter 0
        assert "THE FLAW" in directive
        assert "Wrath" in directive

    def test_world_drives_on_odd_chapters(self, state):
        state.soul_ledger.hamartia_profile = get_hamartia_profile("Wrath")
        _, directive = select_adult_beat(state, 13)  # chapter 1
        assert "THE WORLD" in directive

    def test_bare_state_still_produces_a_driver(self):
        bare = ThreadState()
        _, directive = select_adult_beat(bare, 10)
        assert "THE DRIVER" in directive
