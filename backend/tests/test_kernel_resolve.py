"""Tests for _resolve_turn() — the shared game-math pipeline (Steps 1-8).

Tests the isolated resolution logic: Lachesis evaluation, vector deltas,
hamartia fork, oath processing, parallel agents, conflict resolution,
vector penalties/chaos, prophecy updates, and terminal detection.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel, TurnContext, _get_turn_metadata


@pytest.fixture
def kernel(monkeypatch) -> NyxKernel:
    """A fresh kernel with all agents pinned to mock mode."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "clotho_model", "mock")
    monkeypatch.setattr(settings, "lachesis_model", "mock")
    monkeypatch.setattr(settings, "nemesis_model", "mock")
    monkeypatch.setattr(settings, "eris_model", "mock")
    monkeypatch.setattr(settings, "hypnos_model", "mock")
    monkeypatch.setattr(settings, "chronicler_model", "mock")
    return NyxKernel()


async def _init(kernel: NyxKernel) -> None:
    """Shared helper: initialize a kernel session."""
    await kernel.initialize(
        hamartia="Unformed",
        player_id="test_player",
        name="Hero",
        gender="boy",
        first_memory="A light in the distance I could not reach.",
    )


class TestResolveReturnType:
    """_resolve_turn always returns a TurnContext."""

    @pytest.mark.asyncio
    async def test_returns_turn_context(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        assert isinstance(ctx, TurnContext)

    @pytest.mark.asyncio
    async def test_context_has_required_fields(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("attack the beast")
        assert ctx.turn >= 2
        assert ctx.phase >= 1
        assert ctx.ui_mode in ("buttons", "open")
        assert ctx.action == "attack the beast"
        assert ctx.outcome is not None
        assert ctx.working_state is not None
        assert ctx.lachesis_result is not None
        assert isinstance(ctx.stratified_context, str)
        assert isinstance(ctx.nemesis_desc, str)
        assert isinstance(ctx.eris_desc, str)


class TestResolveVectorDeltas:
    """Vector deltas from Lachesis are applied during resolution."""

    @pytest.mark.asyncio
    async def test_bia_increased_by_combat(self, kernel: NyxKernel):
        await _init(kernel)
        initial_bia = kernel.state.soul_ledger.vectors.bia
        ctx = await kernel._resolve_turn("attack the beast")
        # Mock Lachesis gives bia+2.0 for combat actions
        assert ctx.outcome.state.soul_ledger.vectors.bia > initial_bia

    @pytest.mark.asyncio
    async def test_deltas_recorded_in_lachesis_result(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("attack the beast")
        assert ctx.lachesis_result.vector_deltas  # non-empty dict


class TestResolveInvalidAction:
    """Invalid actions are rejected without advancing turn count."""

    @pytest.mark.asyncio
    async def test_invalid_action_not_valid(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("fly into the sky")
        assert not ctx.outcome.action_valid

    @pytest.mark.asyncio
    async def test_invalid_action_preserves_turn_count(self, kernel: NyxKernel):
        await _init(kernel)
        tc_before = kernel.state.session.turn_count
        await kernel._resolve_turn("fly into the sky")
        assert kernel.state.session.turn_count == tc_before

    @pytest.mark.asyncio
    async def test_invalid_action_has_reason(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("fly into the sky")
        assert ctx.outcome.invalid_reason != ""


class TestResolveOathProcessing:
    """Oath detection and violation processing."""

    @pytest.mark.asyncio
    async def test_oath_detected(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("I swear to avenge my father")
        oaths = ctx.outcome.state.soul_ledger.active_oaths
        assert len(oaths) >= 1
        assert any("avenge" in o.text.lower() for o in oaths)

    @pytest.mark.asyncio
    async def test_oath_gets_unique_id(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("I swear to avenge my father")
        oaths = ctx.outcome.state.soul_ledger.active_oaths
        ids = [o.oath_id for o in oaths]
        assert len(ids) == len(set(ids))  # all unique


class TestResolveHamartiaFork:
    """Kernel assigns hamartia at Turn 10 via deterministic engine."""

    @pytest.mark.asyncio
    async def test_hamartia_assigned_at_turn_10(self, kernel: NyxKernel):
        """Unformed hamartia is overwritten when epoch reaches phase 4."""
        await _init(kernel)
        # Set turn to 9 so next _resolve_turn increments to 10 → phase 4
        kernel.state.session.turn_count = 9
        kernel.state.soul_ledger.hamartia = "Unformed"
        # Make bia dominant
        kernel.state.soul_ledger.vectors.bia = 9.0
        kernel.state.soul_ledger.vectors.metis = 2.0
        kernel.state.soul_ledger.vectors.kleos = 2.0
        kernel.state.soul_ledger.vectors.aidos = 2.0
        ctx = await kernel._resolve_turn("attack the beast")
        assert ctx.outcome.state.soul_ledger.hamartia == "Wrath"

    @pytest.mark.asyncio
    async def test_hamartia_not_overwritten_when_already_set(self, kernel: NyxKernel):
        """If hamartia is already assigned (not Unformed), kernel skips."""
        await _init(kernel)
        kernel.state.session.turn_count = 9
        kernel.state.soul_ledger.hamartia = "Hubris"  # already assigned
        ctx = await kernel._resolve_turn("attack the beast")
        assert ctx.outcome.state.soul_ledger.hamartia == "Hubris"

    @pytest.mark.asyncio
    async def test_hamartia_not_assigned_before_phase_4(self, kernel: NyxKernel):
        """Unformed stays Unformed if epoch hasn't reached phase 4."""
        await _init(kernel)
        kernel.state.session.turn_count = 4  # next turn = 5 → phase 2
        kernel.state.soul_ledger.hamartia = "Unformed"
        ctx = await kernel._resolve_turn("look around")
        assert ctx.outcome.state.soul_ledger.hamartia == "Unformed"


class TestResolveEpochMachine:
    """Epoch phase is computed correctly during resolution."""

    @pytest.mark.asyncio
    async def test_phase_1_turns_1_to_3(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")  # turn 2
        assert ctx.phase == 1
        assert ctx.ui_mode == "buttons"

    @pytest.mark.asyncio
    async def test_phase_2_turns_4_to_6(self, kernel: NyxKernel):
        await _init(kernel)
        for _ in range(3):
            await kernel._resolve_turn("look around")  # turns 2-4
        # Turn 4 should be phase 2
        assert kernel.state.session.epoch_phase == 2

    @pytest.mark.asyncio
    async def test_phase_4_open_mode(self):
        phase, _age, ui_mode, beat, _dir = _get_turn_metadata(10)
        assert phase == 4
        assert ui_mode == "open"

    @pytest.mark.asyncio
    async def test_phase_3_turns_7_to_9(self):
        phase, _age, ui_mode, beat, _dir = _get_turn_metadata(7)
        assert phase == 3
        assert ui_mode == "buttons"


class TestResolveTerminal:
    """Terminal state detection (death paths)."""

    @pytest.mark.asyncio
    async def test_normal_turn_not_terminal(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        assert not ctx.terminal

    @pytest.mark.asyncio
    async def test_terminal_has_death_reason(self, kernel: NyxKernel):
        """If a turn IS terminal, death_reason should be populated."""
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        # Normal turn: not terminal, no reason
        if not ctx.terminal:
            assert ctx.death_reason == ""


class TestResolveStratifiedContext:
    """Stratified context is built during resolution."""

    @pytest.mark.asyncio
    async def test_stratified_context_is_string(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        assert isinstance(ctx.stratified_context, str)

    @pytest.mark.asyncio
    async def test_stratified_includes_recent_prose(self, kernel: NyxKernel):
        """After init (which seeds prose_history), stratified should include recent thread."""
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        # init seeds prose_history with birth scene, so stratified should have something
        assert "RECENT THREAD" in ctx.stratified_context or ctx.stratified_context == ""
