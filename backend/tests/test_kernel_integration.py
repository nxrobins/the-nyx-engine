"""Integration tests for the NyxKernel — full pipeline in mock mode.

Tests the complete flow: initialize() → process_turn() → verify state mutations.
All agents run in mock mode (no LLM calls).
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel


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


class TestKernelInitialize:
    """Turn 0→1: Session initialization."""

    @pytest.mark.asyncio
    async def test_basic_initialization(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Achilles",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        assert result.turn_number == 1
        assert result.prose != ""
        assert result.state.session.player_name == "Achilles"
        assert result.state.session.player_gender == "boy"
        assert result.state.soul_ledger.hamartia == "Unformed"
        assert result.state.session.turn_count == 1
        assert result.state.session.epoch_phase == 1
        assert result.state.session.ui_mode == "buttons"

    @pytest.mark.asyncio
    async def test_memory_seeds_vector(self, kernel: NyxKernel):
        """'light' keyword in first_memory should boost metis +2."""
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Orpheus",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        assert result.state.soul_ledger.vectors.metis == 7.0  # 5.0 + 2.0

    @pytest.mark.asyncio
    async def test_stone_memory_seeds_bia(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Ajax",
            gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        assert result.state.soul_ledger.vectors.bia == 7.0

    @pytest.mark.asyncio
    async def test_invalid_hamartia_defaults(self, kernel: NyxKernel):
        """Invalid hamartia string → defaults to first option."""
        result = await kernel.initialize(
            hamartia="Made Up Flaw",
            player_id="test_player",
            name="Nobody",
            gender="unknown",
        )
        # Should default to first hamartia option
        assert result.state.soul_ledger.hamartia != "Made Up Flaw"

    @pytest.mark.asyncio
    async def test_unformed_hamartia_accepted(self, kernel: NyxKernel):
        """'Unformed' is a valid hamartia (assigned later by Lachesis)."""
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Nobody",
            gender="unknown",
        )
        assert result.state.soul_ledger.hamartia == "Unformed"

    @pytest.mark.asyncio
    async def test_prophecy_generated(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Cassandra",
            gender="girl",
        )
        # Nemesis mock should generate a prophecy
        assert result.state.the_loom.current_prophecy != ""

    @pytest.mark.asyncio
    async def test_prose_history_seeded(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        # Birth scene should be in prose_history
        assert len(result.state.prose_history) >= 1

    @pytest.mark.asyncio
    async def test_ui_choices_present(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        # Phase 1 should have choices (buttons mode)
        assert isinstance(result.ui_choices, list)


class TestWorldSeedIntegration:
    """Sprint 10: World seed is injected at initialization."""

    @pytest.mark.asyncio
    async def test_light_memory_seeds_thornwell(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Orpheus",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        assert "Thornwell" in result.state.world_context

    @pytest.mark.asyncio
    async def test_stone_memory_seeds_ashfall(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Ajax",
            gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        assert "Ashfall" in result.state.world_context

    @pytest.mark.asyncio
    async def test_crowd_memory_seeds_oldgate(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Helen",
            gender="girl",
            first_memory="A crowd shouting a name that was not mine.",
        )
        assert "Oldgate" in result.state.world_context

    @pytest.mark.asyncio
    async def test_shadow_memory_seeds_fenward(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Nyx",
            gender="girl",
            first_memory="A cold shadow that moved when I moved.",
        )
        assert "Fenward" in result.state.world_context

    @pytest.mark.asyncio
    async def test_environment_not_shadowed_threshold(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        assert "shadowed threshold" not in result.state.session.current_environment

    @pytest.mark.asyncio
    async def test_environment_contains_active_situation(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        assert "shaft collapsed" in result.state.session.current_environment

    @pytest.mark.asyncio
    async def test_world_context_nonempty_after_init(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        assert result.state.world_context != ""

    @pytest.mark.asyncio
    async def test_world_context_in_stratified_context(self, kernel: NyxKernel):
        """World context should appear in stratified context via Origin wrapper."""
        from app.core.kernel import _build_stratified_context
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        ctx = _build_stratified_context(kernel.state)
        assert "THE ORIGIN" in ctx
        assert "Thornwell" in ctx

    @pytest.mark.asyncio
    async def test_origin_absent_when_world_context_empty(self, kernel: NyxKernel):
        """If world_context is empty, Origin section should not appear."""
        from app.core.kernel import _build_stratified_context
        # Manually create a state with empty world_context
        from app.schemas.state import ThreadState
        empty_state = ThreadState()
        ctx = _build_stratified_context(empty_state)
        assert "THE ORIGIN" not in ctx


class TestKernelProcessTurn:
    """Turn 1+: Full pipeline execution."""

    @pytest.mark.asyncio
    async def test_basic_turn(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        result = await kernel.process_turn("attack the beast")
        assert result.turn_number == 2
        assert result.prose != ""
        assert result.state.session.turn_count == 2

    @pytest.mark.asyncio
    async def test_vector_deltas_applied(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        initial_bia = kernel.state.soul_ledger.vectors.bia
        result = await kernel.process_turn("attack the beast")
        # Mock Lachesis gives bia+2.0 for combat
        assert result.state.soul_ledger.vectors.bia > initial_bia

    @pytest.mark.asyncio
    async def test_invalid_action_doesnt_increment_turn(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        initial_turn = kernel.state.session.turn_count
        result = await kernel.process_turn("fly into the sky")
        # Invalid action → turn count should not advance
        assert kernel.state.session.turn_count == initial_turn

    @pytest.mark.asyncio
    async def test_epoch_advances(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        # Turns 2-3 are Phase 1
        for _ in range(2):
            await kernel.process_turn("look around")
        assert kernel.state.session.epoch_phase == 1

        # Turn 4 → Phase 2
        await kernel.process_turn("look around")
        assert kernel.state.session.epoch_phase == 2

    @pytest.mark.asyncio
    async def test_oath_registered(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        result = await kernel.process_turn("I swear to avenge my father")
        # Oath should be registered in state
        oaths = result.state.soul_ledger.active_oaths
        assert len(oaths) >= 1
        assert any("avenge" in o.text.lower() for o in oaths)

    @pytest.mark.asyncio
    async def test_multiple_turns_accumulate(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        for i in range(5):
            await kernel.process_turn(f"look around turn {i}")

        assert kernel.state.session.turn_count == 6  # 1 (init) + 5

    @pytest.mark.asyncio
    async def test_prose_history_grows(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        initial_len = len(kernel.state.prose_history)
        await kernel.process_turn("attack")
        assert len(kernel.state.prose_history) > initial_len


class TestKernelReset:
    """Reset clears all state."""

    @pytest.mark.asyncio
    async def test_reset_clears_state(self, kernel: NyxKernel):
        await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
        )
        await kernel.process_turn("attack")
        kernel.reset()

        assert kernel.state.session.turn_count == 0
        assert kernel.state.soul_ledger.hamartia == ""
        assert kernel.state.session.player_name == "Stranger"
