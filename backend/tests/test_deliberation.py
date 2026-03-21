"""Tests for Phase 2 deliberation traces and resolved scene contracts."""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.schemas.state import SoulVectors


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


class TestDeliberationTrace:
    """Resolver output should now include structured traces."""

    @pytest.mark.asyncio
    async def test_resolve_collects_four_agent_proposals(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        assert ctx.deliberation_trace is not None
        agents = {proposal.agent for proposal in ctx.deliberation_trace.proposals}
        assert agents == {"lachesis", "atropos", "nemesis", "eris"}

    @pytest.mark.asyncio
    async def test_invalid_action_gets_lachesis_only_trace(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("fly into the sky")
        assert ctx.deliberation_trace is not None
        assert ctx.deliberation_trace.winner_order == ["lachesis"]
        assert "invalid" in ctx.deliberation_trace.final_reason.lower()

    @pytest.mark.asyncio
    async def test_trace_is_stored_on_committed_state(self, kernel: NyxKernel):
        await _init(kernel)
        await kernel.process_turn("look around")
        assert kernel.state.recent_traces
        assert kernel.state.recent_traces[-1].proposals


class TestResolvedSceneOutcome:
    """Winning interventions should mutate the resolved scene contract."""

    @pytest.mark.asyncio
    async def test_nemesis_updates_scene_carryover(self, kernel: NyxKernel, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "eris_chaos_probability", 0.0)
        await _init(kernel)
        kernel.state.soul_ledger.vectors = SoulVectors(
            metis=1.0, bia=9.0, kleos=1.0, aidos=1.0
        )

        ctx = await kernel._resolve_turn("attack the beast")
        assert ctx.outcome.nemesis_struck is True
        assert ctx.scene_outcome is not None
        assert ctx.deliberation_trace is not None
        assert ctx.deliberation_trace.winner_order == ["lachesis", "nemesis"]
        assert ctx.outcome.state.canon.current_scene.carryover_consequence == ctx.outcome.nemesis_description

    @pytest.mark.asyncio
    async def test_scene_outcome_names_present_npcs(self, kernel: NyxKernel):
        await _init(kernel)
        ctx = await kernel._resolve_turn("look around")
        assert ctx.scene_outcome is not None
        assert ctx.scene_outcome.present_npcs
        assert any(name in {"Sera", "Aldric"} for name in ctx.scene_outcome.present_npcs)
