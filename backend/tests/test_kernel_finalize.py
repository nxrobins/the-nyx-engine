"""Tests for _finalize_turn() — the shared post-prose bookkeeping pipeline.

Tests Momus validation, milestone checks, prose history management,
Chronicler compression, RAG indexing, state commit, and DB persistence.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel, TurnContext
from app.schemas.state import TurnResult


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
    await kernel.initialize(
        hamartia="Unformed",
        player_id="test_player",
        name="Hero",
        gender="boy",
        first_memory="A light in the distance I could not reach.",
    )


async def _get_ctx(kernel: NyxKernel, action: str = "look around") -> TurnContext:
    """Resolve a turn and return the context for finalize testing."""
    return await kernel._resolve_turn(action)


class TestFinalizeReturnType:
    """_finalize_turn returns a properly structured TurnResult."""

    @pytest.mark.asyncio
    async def test_returns_turn_result(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        result = await kernel._finalize_turn(ctx, "Test prose.", ["choice A"])
        assert isinstance(result, TurnResult)

    @pytest.mark.asyncio
    async def test_result_contains_prose(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        result = await kernel._finalize_turn(ctx, "The ash falls.", ["run"])
        assert result.prose == "The ash falls."

    @pytest.mark.asyncio
    async def test_result_contains_choices(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        choices = ["draw sword", "flee", "parley"]
        result = await kernel._finalize_turn(ctx, "prose", choices)
        assert result.ui_choices == choices

    @pytest.mark.asyncio
    async def test_result_not_terminal(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        result = await kernel._finalize_turn(ctx, "prose", [])
        assert not result.terminal

    @pytest.mark.asyncio
    async def test_result_turn_number(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        result = await kernel._finalize_turn(ctx, "prose", [])
        assert result.turn_number == ctx.turn


class TestFinalizeProseHistory:
    """Prose history is tracked and capped."""

    @pytest.mark.asyncio
    async def test_prose_appended_to_history(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        await kernel._finalize_turn(ctx, "New prose.", [])
        assert "New prose." in kernel.state.prose_history

    @pytest.mark.asyncio
    async def test_prose_history_capped(self, kernel: NyxKernel, monkeypatch):
        """Prose history never exceeds chronicle_interval + chronicle_prose_retention."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "chronicle_interval", 5)
        monkeypatch.setattr(settings, "chronicle_prose_retention", 2)
        cap = 7  # 5 + 2

        await _init(kernel)
        # Run many turns to accumulate prose
        for i in range(12):
            ctx = await _get_ctx(kernel, f"action {i}")
            if ctx.outcome.action_valid:
                await kernel._finalize_turn(ctx, f"Prose {i}", [])

        assert len(kernel.state.prose_history) <= cap


class TestFinalizeChronicler:
    """Chronicler compression triggers at the right interval."""

    @pytest.mark.asyncio
    async def test_chronicler_fires_at_interval(self, kernel: NyxKernel, monkeypatch):
        """Chronicle grows when turn is divisible by chronicle_interval."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "chronicle_interval", 3)
        monkeypatch.setattr(settings, "chronicle_prose_retention", 1)

        await _init(kernel)
        # Run turns 2,3 — chronicler fires at turn 3
        for i in range(2):
            ctx = await _get_ctx(kernel, f"look around {i}")
            if ctx.outcome.action_valid:
                await kernel._finalize_turn(ctx, f"Prose turn {i+2}", [])

        # Turn 3 is divisible by 3, chronicler should have fired
        # (turn 1 from init + 2 process_turns = turn 3)
        assert len(kernel.state.chronicle) >= 1

    @pytest.mark.asyncio
    async def test_prose_history_flushed_after_compression(self, kernel: NyxKernel, monkeypatch):
        """After chronicler fires, prose_history is trimmed to retention count."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "chronicle_interval", 3)
        monkeypatch.setattr(settings, "chronicle_prose_retention", 1)

        await _init(kernel)
        for i in range(2):
            ctx = await _get_ctx(kernel, f"action {i}")
            if ctx.outcome.action_valid:
                await kernel._finalize_turn(ctx, f"Prose {i}", [])

        assert len(kernel.state.prose_history) <= 2  # retention + at most 1


class TestFinalizeStateCommit:
    """State is committed to kernel.state after finalization."""

    @pytest.mark.asyncio
    async def test_state_committed(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        result = await kernel._finalize_turn(ctx, "Final prose.", [])
        # kernel.state should reflect the finalized state
        assert kernel.state.session.turn_count >= 2
        assert "Final prose." in kernel.state.prose_history


class TestHandleDeath:
    """_handle_death produces correct terminal TurnResult."""

    @pytest.mark.asyncio
    async def test_death_result_is_terminal(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        # Manually force terminal for testing
        ctx.terminal = True
        ctx.death_reason = "Soul collapsed under its own weight."
        ctx.outcome.terminal = True
        ctx.outcome.death_reason = ctx.death_reason

        result = await kernel._handle_death(ctx)
        assert result.terminal is True
        assert "THREAD SEVERED" in result.prose
        assert result.death_reason == "Soul collapsed under its own weight."

    @pytest.mark.asyncio
    async def test_death_commits_state(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        ctx.terminal = True
        ctx.death_reason = "Eaten by wolves."
        ctx.outcome.terminal = True
        ctx.outcome.death_reason = ctx.death_reason

        await kernel._handle_death(ctx)
        # State should be committed
        assert kernel.state is ctx.outcome.state


class TestAppendInterventions:
    """Static method _append_interventions adds Nemesis/Eris flavor."""

    @pytest.mark.asyncio
    async def test_nemesis_appended(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        ctx.outcome.nemesis_struck = True
        ctx.nemesis_desc = "The Fates remember your arrogance."
        result = NyxKernel._append_interventions("Base prose.", ctx)
        assert "The Fates remember your arrogance." in result

    @pytest.mark.asyncio
    async def test_eris_appended(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        ctx.outcome.eris_struck = True
        ctx.eris_desc = "A wild tremor shakes the ground."
        result = NyxKernel._append_interventions("Base prose.", ctx)
        assert "A wild tremor shakes the ground." in result

    @pytest.mark.asyncio
    async def test_no_intervention_unchanged(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        ctx.outcome.nemesis_struck = False
        ctx.outcome.eris_struck = False
        result = NyxKernel._append_interventions("Base prose.", ctx)
        assert result == "Base prose."

    @pytest.mark.asyncio
    async def test_both_interventions_appended(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await _get_ctx(kernel)
        ctx.outcome.nemesis_struck = True
        ctx.outcome.eris_struck = True
        ctx.nemesis_desc = "Nemesis strikes."
        ctx.eris_desc = "Eris laughs."
        result = NyxKernel._append_interventions("Base.", ctx)
        assert "Nemesis strikes." in result
        assert "Eris laughs." in result
