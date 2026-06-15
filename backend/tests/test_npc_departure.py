"""The Witnesses Leave — deep betrayal departs an NPC from your life.

Builds on the merged relationship ledger (Sprint D): a present, living NPC whose
betrayal_weight crosses the no-return threshold departs (status -> "departed") —
gone from every future scene via _alive_present_ids, but still in canon.npcs and
still remembered (their betrayals remain in npc.events). Deterministic, zero LLM.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.schemas.state import CanonNPC, SceneState, SessionData, ThreadState, WorldCanon
from app.services.canon import (
    _alive_present_ids,
    maybe_depart_npcs,
    render_scene_snapshot,
    update_npc_relations,
)


class _Outcome:
    def __init__(self, action_valid: bool = True, oath_broken=None):
        self.action_valid = action_valid
        self.oath_broken = oath_broken


def _npc(name: str, role: str = "mother", **kw) -> CanonNPC:
    return CanonNPC(
        npc_id=f"npc_{name.lower()}", name=name, role=role,
        home_location_id="home", current_location_id="home", **kw,
    )


def _state(*npcs: CanonNPC, turn: int = 5) -> ThreadState:
    canon = WorldCanon(
        npcs={n.npc_id: n for n in npcs},
        current_scene=SceneState(
            scene_id="s", location_id="home",
            present_npc_ids=[n.npc_id for n in npcs],
        ),
    )
    return ThreadState(session=SessionData(turn_count=turn), canon=canon)


class TestDeparture:
    def test_departs_at_threshold(self):
        sera = _npc("Sera", betrayal_weight=settings.npc_depart_betrayal_weight)
        st = _state(sera)
        notes = maybe_depart_npcs(st)
        assert sera.status == "departed"
        assert notes and "Sera" in notes[0]
        assert "npc_sera" not in st.canon.current_scene.present_npc_ids   # removed from the cast

    def test_stays_below_threshold(self):
        sera = _npc("Sera", betrayal_weight=settings.npc_depart_betrayal_weight - 0.5)
        st = _state(sera)
        assert maybe_depart_npcs(st) == []
        assert sera.status == "alive"
        assert "npc_sera" in st.canon.current_scene.present_npc_ids

    def test_departed_is_remembered_not_erased(self):
        sera = _npc("Sera", betrayal_weight=6.0, betrayal_count=4)
        st = _state(sera)
        maybe_depart_npcs(st)
        # gone from the scene, but still in canon (the ledger/book still remember).
        assert "npc_sera" in st.canon.npcs
        assert st.canon.npcs["npc_sera"].status == "departed"
        assert st.canon.npcs["npc_sera"].betrayal_count == 4   # the record stands

    def test_idempotent(self):
        sera = _npc("Sera", betrayal_weight=6.0)
        st = _state(sera)
        first = maybe_depart_npcs(st)
        second = maybe_depart_npcs(st)        # already departed -> no longer "alive"
        assert first and second == []

    def test_render_excludes_the_departed(self):
        sera, kael = _npc("Sera"), _npc("Kael", "father", betrayal_weight=6.0)
        st = _state(sera, kael)
        maybe_depart_npcs(st)
        assert _alive_present_ids(st.canon, st.canon.current_scene.present_npc_ids) == ["npc_sera"]
        snap = render_scene_snapshot(st)
        assert "Kael" not in snap and "Sera" in snap

    def test_empty_cast_is_fine(self):
        kael = _npc("Kael", "father", betrayal_weight=6.0)
        st = _state(kael)
        maybe_depart_npcs(st)
        assert st.canon.current_scene.present_npc_ids == []   # alienated everyone — earned solitude

    def test_four_betrayals_cross_the_threshold(self):
        # The ledger math: 4 deliberate betrayals push betrayal_weight past 5.0.
        sera = _npc("Sera")
        st = _state(sera)
        for _ in range(3):
            update_npc_relations(st, "I betray Sera", _Outcome())
        assert sera.betrayal_weight < settings.npc_depart_betrayal_weight
        assert maybe_depart_npcs(st) == []                    # three is not yet past returning
        update_npc_relations(st, "I betray Sera", _Outcome())
        assert sera.betrayal_weight >= settings.npc_depart_betrayal_weight
        assert maybe_depart_npcs(st)                          # the fourth is
        assert sera.status == "departed"


class TestKernelWiring:
    @pytest.mark.asyncio
    async def test_betrayed_npc_departs_through_the_kernel(self):
        k = NyxKernel()
        await k.initialize(
            hamartia="Hubris of the Intellect", player_id="leave",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",  # Thornwell: Sera present
        )
        sera = k.state.canon.npcs["npc_sera"]
        sera.betrayal_weight = settings.npc_depart_betrayal_weight   # already past returning
        result = await k.process_turn("walk to the well")            # any turn runs step 8d'
        assert not result.terminal
        assert k.state.canon.npcs["npc_sera"].status == "departed"
        assert "npc_sera" not in k.state.canon.current_scene.present_npc_ids
