"""The Witnesses Arrive — the deterministic arrival mechanism (canon level).

A world may author LATENT NPCs that ENTER an established life when an earned,
machine-checkable condition is met. These pin the mechanism in isolation
(hand-built latent canon); the authoring path, kernel wiring, and the API
no-leak strip land in the next slice. Hermetic, keyless — no model, no RNG.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from app.core.config import settings
from app.core.world_seeds import WORLD_SEEDS, SeedArrival, SeedLatentNPC
from app.schemas.state import (
    ArrivalCondition,
    CanonNPC,
    SceneClock,
    SceneState,
    SessionData,
    ThreadState,
    WorldCanon,
)
from app.services.canon import (
    _arrival_eligible,
    bootstrap_canon,
    client_safe_state,
    maybe_arrive_npcs,
)


def _npc(npc_id, name, *, status="latent", cond=None, bond=0.0, role="stranger"):
    return CanonNPC(
        npc_id=npc_id, name=name, role=role,
        home_location_id="home", current_location_id="home",
        status=status, bond=bond, arrival_condition=cond,
    )


def _state(turn, *npcs, present=(), doom_active=False, clocks=None):
    canon = WorldCanon(
        npcs={n.npc_id: n for n in npcs},
        clocks={c.clock_id: c for c in (clocks or [])},
        current_scene=SceneState(
            scene_id="s", location_id="home", present_npc_ids=list(present),
        ),
    )
    st = ThreadState(session=SessionData(turn_count=turn), canon=canon)
    st.doom.active = doom_active
    return st


class TestArrivalEligibility:
    def test_vacuous_condition_never_arrives(self):
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition())  # all-default = vacuous
        st = _state(200, npc)
        assert maybe_arrive_npcs(st).arrived_id is None
        assert npc.status == "latent"

    def test_no_condition_never_arrives(self):
        assert maybe_arrive_npcs(_state(50, _npc("npc_a", "Ada", cond=None))).arrived_id is None

    def test_childhood_is_sealed(self):
        # min_turn=2 cannot lower the global adult floor of 10.
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=2))
        for t in range(2, 10):
            assert maybe_arrive_npcs(_state(t, _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=2)))).arrived_id is None
        assert maybe_arrive_npcs(_state(10, npc)).arrived_id == "npc_a"

    def test_min_turn_gate(self):
        assert maybe_arrive_npcs(_state(14, _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=15)))).arrived_id is None
        assert maybe_arrive_npcs(_state(15, _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=15)))).arrived_id == "npc_a"

    def test_bond_gate_met(self):
        anchor = _npc("npc_mara", "Mara", status="alive", bond=7.0, role="friend")
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(requires_bond_npc_id="npc_mara", requires_bond_at_least=6.0))
        assert maybe_arrive_npcs(_state(12, anchor, late, present=["npc_mara"])).arrived_id == "npc_a"

    def test_bond_gate_unmet_when_cold(self):
        anchor = _npc("npc_mara", "Mara", status="alive", bond=1.0, role="friend")
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(requires_bond_npc_id="npc_mara", requires_bond_at_least=6.0))
        assert maybe_arrive_npcs(_state(12, anchor, late, present=["npc_mara"])).arrived_id is None

    def test_bond_gate_unmet_when_anchor_gone(self):
        # The anchor-gone tragedy falls out for free — a departed friend can't draw anyone in.
        anchor = _npc("npc_mara", "Mara", status="departed", bond=9.0, role="friend")
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(requires_bond_npc_id="npc_mara", requires_bond_at_least=6.0))
        assert maybe_arrive_npcs(_state(12, anchor, late)).arrived_id is None

    def test_clock_resolved_gate(self):
        clk = SceneClock(clock_id="clock_storm", label="Storm", progress=4, max_segments=4)
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(on_clock_resolved="clock_storm"))
        assert maybe_arrive_npcs(_state(12, late, clocks=[clk])).arrived_id == "npc_a"

    def test_clock_unresolved_gate(self):
        clk = SceneClock(clock_id="clock_storm", label="Storm", progress=2, max_segments=4)
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(on_clock_resolved="clock_storm"))
        assert maybe_arrive_npcs(_state(12, late, clocks=[clk])).arrived_id is None

    def test_claiming_clock_never_summons(self):
        # A clock that TAKES a life may not also summon an arrival (ARR-C7).
        clk = SceneClock(clock_id="clock_doom", label="Doom", progress=4, max_segments=4, claims_npc_id="npc_x")
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(on_clock_resolved="clock_doom"))
        assert maybe_arrive_npcs(_state(12, late, clocks=[clk])).arrived_id is None


class TestArrivalMechanism:
    def test_doom_suppresses_arrival(self):
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10))
        st = _state(12, npc, doom_active=True)
        assert maybe_arrive_npcs(st).arrived_id is None
        assert npc.status == "latent"

    def test_cast_cap_blocks_then_clears(self):
        present = [f"npc_p{i}" for i in range(settings.arrival_present_cap)]
        crowd = [_npc(pid, pid, status="alive") for pid in present]
        late = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10))
        st = _state(12, *crowd, late, present=present)
        assert maybe_arrive_npcs(st).arrived_id is None        # cast full
        st.canon.npcs[present[0]].status = "departed"           # a slot frees
        st.canon.current_scene.present_npc_ids = present[1:]
        assert maybe_arrive_npcs(st).arrived_id == "npc_a"

    def test_promotes_relocates_and_appends(self):
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10))
        st = _state(12, npc)
        res = maybe_arrive_npcs(st)
        assert res.arrived_id == "npc_a"
        arrived = st.canon.npcs["npc_a"]
        assert arrived.status == "alive"
        assert arrived.arrived_turn == 12
        assert arrived.current_location_id == "home"
        assert "npc_a" in st.canon.current_scene.present_npc_ids
        assert any(e.kind == "arrived" for e in arrived.events)
        assert res.notes and "Ada" in res.notes[0]

    def test_at_most_one_and_priority_tiebreak(self):
        first = _npc("npc_z", "Zed", cond=ArrivalCondition(min_turn=10, arrival_priority=1))
        second = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10, arrival_priority=5))
        st = _state(12, first, second)
        assert maybe_arrive_npcs(st).arrived_id == "npc_z"      # priority 1 < 5
        assert st.canon.npcs["npc_a"].status == "latent"        # the other waits

    def test_never_resurrects_non_latent(self):
        dead = _npc("npc_d", "Dorn", status="dead", cond=ArrivalCondition(min_turn=10))
        departed = _npc("npc_e", "Esa", status="departed", cond=ArrivalCondition(min_turn=10))
        st = _state(50, dead, departed)
        assert maybe_arrive_npcs(st).arrived_id is None
        assert st.canon.npcs["npc_d"].status == "dead"
        assert st.canon.npcs["npc_e"].status == "departed"

    def test_idempotent_after_arrival(self):
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10))
        st = _state(12, npc)
        assert maybe_arrive_npcs(st).arrived_id == "npc_a"
        assert maybe_arrive_npcs(st).arrived_id is None         # already alive

    def test_soul_pressures_doom_untouched(self):
        npc = _npc("npc_a", "Ada", cond=ArrivalCondition(min_turn=10))
        st = _state(12, npc)
        soul_before = copy.deepcopy(st.soul_ledger)
        pressures_before = copy.deepcopy(st.pressures)
        doom_before = copy.deepcopy(st.doom)
        maybe_arrive_npcs(st)
        assert st.soul_ledger == soul_before
        assert st.pressures == pressures_before
        assert st.doom == doom_before


class TestBootstrapAuthoring:
    """A seed may carry latent NPCs; bootstrap mints them as status='latent'
    (absent at birth), and they arrive end-to-end through maybe_arrive_npcs."""

    def test_bootstrap_mints_a_latent_npc(self):
        seed = dataclasses.replace(WORLD_SEEDS["light"], latent=[
            SeedLatentNPC(name="Kael", role="ally", arrival=SeedArrival(min_turn=12)),
        ])
        canon = bootstrap_canon(seed, "Orin", "unknown")
        kael = canon.npcs["npc_kael"]
        assert kael.status == "latent"
        assert kael.arrival_condition is not None and kael.arrival_condition.min_turn == 12
        assert "npc_kael" not in canon.current_scene.present_npc_ids   # absent at birth
        assert canon.current_scene.present_npc_ids                     # family still present

    def test_builtins_mint_no_latent(self):
        for key in WORLD_SEEDS:
            canon = bootstrap_canon(WORLD_SEEDS[key], "Orin", "unknown")
            assert not any(n.status == "latent" for n in canon.npcs.values()), key

    def test_seeded_latent_arrives_end_to_end(self):
        seed = dataclasses.replace(WORLD_SEEDS["light"], latent=[
            SeedLatentNPC(name="Kael", role="ally", arrival=SeedArrival(min_turn=12)),
        ])
        canon = bootstrap_canon(seed, "Orin", "unknown")
        st = ThreadState(session=SessionData(turn_count=12), canon=canon)
        res = maybe_arrive_npcs(st)
        assert res.arrived_id == "npc_kael"
        assert canon.npcs["npc_kael"].status == "alive"
        assert "npc_kael" in canon.current_scene.present_npc_ids

    def test_latent_id_collision_is_skipped(self):
        # A latent NPC whose slug collides with a family member is skipped, never
        # overwriting the living one.
        seed = dataclasses.replace(WORLD_SEEDS["light"], latent=[
            SeedLatentNPC(name="Sera", role="stranger", arrival=SeedArrival(min_turn=12)),
        ])
        canon = bootstrap_canon(seed, "Orin", "unknown")
        assert canon.npcs["npc_sera"].status == "alive"   # the family Sera, untouched


class TestClientSafeState:
    """ARR-C14: the unsprung (latent) cast never leaks; the real state keeps it."""

    def test_strips_latent_keeps_the_rest(self):
        st = _state(
            12,
            _npc("npc_a", "Ada", status="alive"),
            _npc("npc_b", "Ben", status="latent", cond=ArrivalCondition(min_turn=10)),
            _npc("npc_c", "Cal", status="dead"),
            present=["npc_a"],
        )
        safe = client_safe_state(st)
        assert "npc_b" not in safe.canon.npcs        # latent stripped from the wire
        assert "npc_a" in safe.canon.npcs            # alive kept
        assert "npc_c" in safe.canon.npcs            # dead kept (canon truth)
        assert "npc_b" in st.canon.npcs              # the REAL state is untouched
        assert "Ben" not in json.dumps(safe.model_dump())

    def test_fast_path_no_latent_returns_same_object(self):
        st = _state(12, _npc("npc_a", "Ada", status="alive"), present=["npc_a"])
        assert client_safe_state(st) is st           # no copy when nothing is latent

    def test_no_canon_is_safe(self):
        st = ThreadState(session=SessionData(turn_count=1))
        assert client_safe_state(st) is st


class TestApiLatentStrip:
    """ARR-C14 at the wire: /state and /action never expose a latent NPC."""

    @pytest.fixture
    def api_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.routes import router

        api = FastAPI()
        api.include_router(router, prefix="/api")
        return TestClient(api)

    def _init(self, api_client, player_id="arr_strip"):
        resp = api_client.post("/api/init", json={
            "hamartia": "Hubris of the Intellect", "player_id": player_id,
            "name": "Orin", "gender": "boy",
            "first_memory": "A light in the distance I could not reach.",
        })
        assert resp.status_code == 200, resp.text
        return resp.json()["session_id"]

    def test_latent_npc_never_reaches_the_client(self, api_client):
        from app.api.routes import _sessions

        sid = self._init(api_client)
        kernel = _sessions[sid].kernel
        kernel.state.canon.npcs["npc_ghost"] = CanonNPC(
            npc_id="npc_ghost", name="Ghostwright", role="ally",
            home_location_id="home", current_location_id="home",
            status="latent", arrival_condition=ArrivalCondition(min_turn=10),
        )
        # /state strips it...
        state = api_client.get(f"/api/state?session_id={sid}").json()
        assert "npc_ghost" not in state["canon"]["npcs"]
        assert "Ghostwright" not in json.dumps(state)
        # ...but the REAL kernel state keeps it (it must persist to arrive)...
        assert "npc_ghost" in kernel.state.canon.npcs
        # ...and /action also strips it from the returned state.
        act = api_client.post("/api/action", json={"session_id": sid, "action": "look around"}).json()
        assert "npc_ghost" not in act["state"]["canon"]["npcs"]
        assert "Ghostwright" not in json.dumps(act["state"])
