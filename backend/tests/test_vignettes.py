"""Vignette contract v0 + builtin pools + selection (THE PULSE, sub-slice 2).

The hardened constraints are Pydantic validators, so these tests are the proof
that the lint is executable: P1-C2 caps, P1-C3 movement floor, the vector-span
rule, slot hygiene — plus a full walk of the four hand-authored builtin pools
and the deterministic selector/binder.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.vignette_pools import _POOLS, pool_for_world
from app.schemas.state import CanonNPC, ThreadState, WorldCanon
from app.schemas.vignette import (
    ConsequencePacket,
    Vignette,
    VignetteChoice,
    VignettePool,
)
from app.services.vignettes import select_vignette


def _ok_choice(vec: str, mag: float = 0.5) -> VignetteChoice:
    return VignetteChoice(
        label=f"Do the {vec} thing",
        packet=ConsequencePacket(vector_deltas={vec: mag}),
    )


def _ok_vignette(**overrides) -> Vignette:
    base = dict(
        vignette_id="test_vignette",
        situation="A concrete situation happens in a specific place nearby.",
        choices=[_ok_choice("bia"), _ok_choice("metis"), _ok_choice("aidos")],
    )
    base.update(overrides)
    return Vignette(**base)


class TestPacketLint:
    def test_vector_cap_rejected(self):
        with pytest.raises(ValidationError, match="P1-C2"):
            ConsequencePacket(vector_deltas={"bia": 1.6})

    def test_pressure_cap_rejected(self):
        with pytest.raises(ValidationError, match="P1-C2"):
            ConsequencePacket(vector_deltas={"bia": 0.5}, pressure_deltas={"omen": 1.1})

    def test_bond_cap_rejected(self):
        with pytest.raises(ValidationError, match="P1-C2"):
            ConsequencePacket(vector_deltas={"bia": 0.5}, bond_delta=2.0)

    def test_unknown_keys_rejected(self):
        with pytest.raises(ValidationError, match="unknown vector"):
            ConsequencePacket(vector_deltas={"hp": 1.0})
        with pytest.raises(ValidationError, match="unknown pressure"):
            ConsequencePacket(pressure_deltas={"mana": 0.5}, vector_deltas={"bia": 0.5})

    def test_movement_floor_rejected(self):
        # Motion theater: all deltas below the floor and no evolution (P1-C3).
        with pytest.raises(ValidationError, match="P1-C3"):
            ConsequencePacket(vector_deltas={"bia": 0.01})

    def test_evolution_alone_satisfies_the_floor(self):
        p = ConsequencePacket(scene_evolution="The door is now barred from inside.")
        assert p.dominant_vector() == ""


class TestVignetteLint:
    def test_vector_span_enforced(self):
        with pytest.raises(ValidationError, match="spans"):
            _ok_vignette(choices=[_ok_choice("bia"), _ok_choice("bia"), _ok_choice("bia")])

    def test_undeclared_slot_rejected(self):
        with pytest.raises(ValidationError, match="undeclared slots"):
            _ok_vignette(situation="Then {mother} arrives with news of the road today.")

    def test_declared_slot_accepted(self):
        v = _ok_vignette(
            situation="Then {mother} arrives with news of the road today.",
            cast_slots=["mother"],
        )
        assert v.cast_slots == ["mother"]

    def test_pool_rejects_duplicate_ids(self):
        with pytest.raises(ValidationError, match="duplicate"):
            VignettePool(world_id="test-world", vignettes=[_ok_vignette(), _ok_vignette()])


class TestBuiltinPools:
    """The hand-authored decks are valid by construction (schema validates at
    import) — these walk their CONTENT guarantees."""

    def test_all_four_builtin_worlds_have_pools(self):
        for world_id in ("builtin-light", "builtin-stone", "builtin-crowd", "builtin-shadow"):
            pool = pool_for_world(world_id)
            assert pool is not None and len(pool.vignettes) >= 5

    def test_every_vignette_covers_adult_entry(self):
        # Phase 1 wires adulthood; each deck must be playable at 18.
        for pool in _POOLS.values():
            playable_at_18 = [v for v in pool.vignettes if v.min_age <= 18 <= v.max_age]
            assert len(playable_at_18) >= 4, pool.world_id

    def test_unknown_world_is_a_dry_pool(self):
        assert pool_for_world("no-such-world") is None


def _adult_state(world_id: str = "builtin-light", age: int = 24) -> ThreadState:
    s = ThreadState()
    s.session.player_id = "p1"
    s.session.turn_count = 12
    s.session.player_age = age
    s.world_id = world_id
    s.canon = WorldCanon(npcs={
        "npc_sera": CanonNPC(
            npc_id="npc_sera", name="Sera", role="mother",
            home_location_id="loc", current_location_id="loc", status="alive",
        ),
    })
    return s


class TestSelection:
    def test_selection_is_deterministic(self):
        s = _adult_state()
        pool = pool_for_world("builtin-light")
        a = select_vignette(s, pool)
        b = select_vignette(s, pool)
        assert a is not None and a.vignette_id == b.vignette_id

    def test_no_repeat_within_a_life(self):
        s = _adult_state()
        pool = pool_for_world("builtin-light")
        seen: set[str] = set()
        for _ in range(len(pool.vignettes)):
            bound = select_vignette(s, pool)
            if bound is None:
                break
            assert bound.vignette_id not in seen
            seen.add(bound.vignette_id)
            s.used_vignette_ids.append(bound.vignette_id)
        # Exhausted deck is a DRY pool, loudly None — the fallback seam.
        assert select_vignette(s, pool) is None

    def test_cast_slot_binds_a_living_name(self):
        s = _adult_state()
        pool = pool_for_world("builtin-light")
        # Burn the deck until the mother-cast vignette comes up.
        for _ in range(len(pool.vignettes)):
            bound = select_vignette(s, pool)
            assert bound is not None
            if bound.cast_names:
                assert bound.cast_names.get("mother") == "Sera"
                assert "Sera" in bound.situation and "{mother}" not in bound.situation
                return
            s.used_vignette_ids.append(bound.vignette_id)
        pytest.fail("no cast-slot vignette surfaced in the deck")

    def test_dead_cast_makes_vignette_ineligible(self):
        s = _adult_state()
        s.canon.npcs["npc_sera"].status = "dead"
        pool = pool_for_world("builtin-light")
        for _ in range(len(pool.vignettes) + 1):
            bound = select_vignette(s, pool)
            if bound is None:
                break
            assert not bound.cast_names, "a dead mother's vignette was selected"
            s.used_vignette_ids.append(bound.vignette_id)

    def test_age_band_filters(self):
        s = _adult_state(age=2)   # infancy: nothing in the adult decks fits
        assert select_vignette(s, pool_for_world("builtin-light")) is None
