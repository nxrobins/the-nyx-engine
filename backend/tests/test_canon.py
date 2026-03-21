"""Tests for the canonical world state helpers."""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.core.world_seeds import WORLD_SEEDS, get_world_seed
from app.services.canon import (
    advance_scene,
    bootstrap_canon,
    derive_environment_string,
    render_scene_snapshot,
)
from app.schemas.state import SessionData, ThreadState


class TestBootstrapCanon:
    """bootstrap_canon() should create stable structured state."""

    def test_bootstrap_creates_named_family_npcs(self):
        for seed in WORLD_SEEDS.values():
            canon = bootstrap_canon(seed, "Hero", "boy")
            names = {npc.name for npc in canon.npcs.values()}
            expected = {npc.name for npc in seed.family}
            assert expected.issubset(names)

    def test_bootstrap_creates_current_scene(self):
        seed = get_world_seed("A light in the distance I could not reach.")
        canon = bootstrap_canon(seed, "Hero", "boy")
        assert canon.current_scene is not None
        assert canon.current_scene.location_id == seed.home_location_id
        assert canon.current_scene.present_npc_ids

    def test_bootstrap_carries_world_facts(self):
        seed = get_world_seed("A crowd shouting a name that was not mine.")
        canon = bootstrap_canon(seed, "Hero", "boy")
        assert canon.world_facts[:3] == seed.world_facts[:3]


class TestCanonRendering:
    """Snapshot and environment rendering stay compact and stable."""

    def test_derive_environment_string_reflects_active_scene(self):
        seed = get_world_seed("The weight of a heavy stone in my hand.")
        canon = bootstrap_canon(seed, "Ajax", "boy")
        state = ThreadState(
            session=SessionData(turn_count=1),
            canon=canon,
        )
        env = derive_environment_string(state)
        assert seed.home_location_name in env
        assert "shaft" in env.lower()

    def test_render_scene_snapshot_is_stable(self):
        seed = get_world_seed("A light in the distance I could not reach.")
        state = ThreadState(
            session=SessionData(turn_count=1),
            canon=bootstrap_canon(seed, "Orpheus", "boy"),
        )
        snap1 = render_scene_snapshot(state)
        snap2 = render_scene_snapshot(state)
        assert snap1 == snap2
        assert "CURRENT LOCATION" in snap1
        assert len(snap1) < 1200

    def test_dead_npc_stays_dead_when_scene_advances(self):
        seed = get_world_seed("A crowd shouting a name that was not mine.")
        state = ThreadState(
            session=SessionData(turn_count=2),
            canon=bootstrap_canon(seed, "Helen", "girl"),
        )
        npc_id = next(iter(state.canon.npcs))
        state.canon.npcs[npc_id].status = "dead"

        advance_scene(
            state,
            immediate_problem="The crowd surges toward the soldiers.",
            carryover_consequence="People remember who froze and who shouted.",
        )

        assert state.canon.npcs[npc_id].status == "dead"
        assert npc_id not in state.canon.current_scene.present_npc_ids


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


class TestKernelCanonIntegration:
    """Kernel initialization should seed canonical state."""

    @pytest.mark.asyncio
    async def test_initialize_sets_thread_canon(self, kernel: NyxKernel):
        result = await kernel.initialize(
            hamartia="Unformed",
            player_id="test_player",
            name="Hero",
            gender="boy",
            first_memory="A cold shadow that moved when I moved.",
        )
        assert result.state.canon is not None
        assert result.state.canon.current_scene is not None
        assert result.state.session.current_environment != ""
