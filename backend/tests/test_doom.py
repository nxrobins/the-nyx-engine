"""Doom Engine tests — staged death, escape routes, and kernel integration."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.schemas.state import Oath, OathTerms, ThreadState
from app.services.doom import (
    advance_doom,
    begin_doom,
    doom_death_reason,
    doom_directive,
    is_doom_terminal,
    maybe_begin_pressure_dooms,
)


@pytest.fixture
def state() -> ThreadState:
    return ThreadState()


class TestBeginDoom:
    def test_begin_sets_stage_one(self, state):
        assert begin_doom(state, cause="broken_oath", description="x") is True
        assert state.doom.active
        assert state.doom.stage == 1
        assert state.doom.max_stage == 3
        assert not state.doom.escapable

    def test_inescapable_doom_is_never_replaced(self, state):
        begin_doom(state, cause="broken_oath", description="first")
        assert begin_doom(state, cause="wounds", description="second", escapable=True) is False
        assert state.doom.cause == "broken_oath"

    def test_escapable_doom_upgrades_to_inescapable(self, state):
        begin_doom(state, cause="wounds", description="bleeding", escapable=True)
        assert begin_doom(state, cause="broken_oath", description="sworn") is True
        assert state.doom.cause == "broken_oath"
        assert not state.doom.escapable

    def test_escapable_doom_does_not_replace_escapable(self, state):
        begin_doom(state, cause="wounds", description="bleeding", escapable=True)
        assert begin_doom(state, cause="faction_heat", description="hunted", escapable=True) is False
        assert state.doom.cause == "wounds"


class TestAdvanceDoom:
    def test_advances_one_stage_per_call(self, state):
        begin_doom(state, cause="broken_oath", description="x", max_stage=3)
        advance_doom(state)
        assert state.doom.stage == 2
        advance_doom(state)
        assert state.doom.stage == 3
        assert is_doom_terminal(state)

    def test_inactive_doom_is_noop(self, state):
        assert advance_doom(state) == ""
        assert not state.doom.active

    def test_stage_caps_at_max(self, state):
        begin_doom(state, cause="broken_oath", description="x", max_stage=2)
        advance_doom(state)
        advance_doom(state)
        assert state.doom.stage == 2

    def test_wounds_doom_lifts_when_answered(self, state):
        state.pressures.wounds = settings.wounds_doom_threshold
        maybe_begin_pressure_dooms(state)
        assert state.doom.active and state.doom.cause == "wounds"

        state.pressures.wounds = settings.wounds_doom_escape - 0.1
        note = advance_doom(state)
        assert "lifts" in note
        assert not state.doom.active

    def test_wounds_doom_holds_while_unanswered(self, state):
        state.pressures.wounds = settings.wounds_doom_threshold
        maybe_begin_pressure_dooms(state)
        state.pressures.wounds = settings.wounds_doom_escape + 0.5
        advance_doom(state)
        assert state.doom.active
        assert state.doom.stage == 2


class TestPressureDooms:
    def test_wounds_threshold_starts_doom(self, state):
        state.pressures.wounds = settings.wounds_doom_threshold
        note = maybe_begin_pressure_dooms(state)
        assert note
        assert state.doom.cause == "wounds"
        assert state.doom.escapable

    def test_faction_heat_threshold_starts_doom(self, state):
        state.pressures.faction_heat = settings.faction_doom_threshold
        note = maybe_begin_pressure_dooms(state)
        assert note
        assert state.doom.cause == "faction_heat"

    def test_below_threshold_no_doom(self, state):
        state.pressures.wounds = settings.wounds_doom_threshold - 0.5
        assert maybe_begin_pressure_dooms(state) == ""
        assert not state.doom.active

    def test_active_doom_blocks_new_pressure_doom(self, state):
        begin_doom(state, cause="broken_oath", description="x")
        state.pressures.wounds = 10.0
        assert maybe_begin_pressure_dooms(state) == ""
        assert state.doom.cause == "broken_oath"


class TestDoomText:
    def test_directive_empty_when_inactive(self, state):
        assert doom_directive(state) == ""

    def test_directive_escalates_with_stage(self, state):
        begin_doom(state, cause="broken_oath", description="The oath broke.", max_stage=3)
        early = doom_directive(state)
        state.doom.stage = 3
        final = doom_directive(state)
        assert "DOOM IS ACTIVE (1/3)" in early
        assert "THIS SCENE" in final

    def test_escapable_directive_names_the_way_out(self, state):
        begin_doom(
            state, cause="wounds", description="Bleeding.",
            escapable=True, escape_hint="Find a healer.",
        )
        assert "Find a healer." in doom_directive(state)

    def test_death_reason_by_cause(self, state):
        begin_doom(state, cause="broken_oath", description="x")
        assert "oath" in doom_death_reason(state).lower()


class TestOathDoomThroughKernel:
    """Breaking an oath stages death over three turns instead of instant sever."""

    @pytest.fixture
    def kernel(self) -> NyxKernel:
        return NyxKernel()

    @pytest.fixture(autouse=True)
    def _no_eris(self, monkeypatch):
        # Pin chaos off: a miracle reprieve would make the death turn flaky.
        import app.agents.eris as eris_module
        monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)

    async def _init(self, kernel: NyxKernel) -> None:
        await kernel.initialize(
            hamartia="Wrath of the Untempered",
            player_id="test_doom",
            name="Orestes",
            gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        kernel.state.soul_ledger.active_oaths.append(
            Oath(
                oath_id="oath_test",
                text="I swear to protect Maren.",
                turn_sworn=1,
                terms=OathTerms(
                    subject="Orestes",
                    promised_action="protect Maren",
                    protected_target="Maren",
                ),
            )
        )

    @pytest.mark.asyncio
    async def test_oath_break_does_not_kill_instantly(self, kernel):
        await self._init(kernel)
        result = await kernel.process_turn("attack Maren")
        assert not result.terminal
        assert kernel.state.doom.active
        assert kernel.state.doom.cause == "broken_oath"
        assert kernel.state.doom.stage == 1

    @pytest.mark.asyncio
    async def test_oath_doom_matures_to_death(self, kernel):
        await self._init(kernel)
        r1 = await kernel.process_turn("attack Maren")
        assert not r1.terminal

        r2 = await kernel.process_turn("look around")
        assert not r2.terminal
        assert kernel.state.doom.stage == 2

        r3 = await kernel.process_turn("wait")
        assert r3.terminal
        assert r3.death_reason
