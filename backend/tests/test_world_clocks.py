"""World Breadth — authored scene clocks (consumption + lethality rails).

Covers the hermetic Nyx half of "The Library Breathes": cartridge clocks reach
the runtime (round-trip), bootstrap_canon instantiates them as live ticking
SceneClocks, and the lethality rails hold — at the LOADER, the real security
boundary, so a hand-dropped cartridge that never saw the autonovel gate is still
safe (WB-C1/C2/C4). Empty-clock builtins are untouched (the keystone holds).
"""

from __future__ import annotations

import pytest

from app.core.kernel import _ADULT_START_TURN, _doom_from_lethal_clock
from app.core.world_seeds import SeedClock, WorldNPC, WorldSeed
from app.schemas.cartridge import WorldCartridge
from app.schemas.state import SceneClock, SessionData, ThreadState
from app.services.canon import _instantiate_authored_clocks, bootstrap_canon
from app.services.doom import is_doom_terminal


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _seed(clocks: list[SeedClock]) -> WorldSeed:
    """A minimal valid WorldSeed carrying the given authored clocks."""
    return WorldSeed(
        settlement="Saltmere",
        settlement_type="drowned hamlet",
        region="the Fens",
        family=[WorldNPC("Gran", "grandmother", "silent")],
        social_class="eel-trappers",
        active_situation="The tide came early.",
        world_facts=["Salt rots the timber", "Eels run on the dark moon"],
        home_location_id="saltmere_house",
        home_location_name="The stilt-house",
        home_location_kind="hovel",
        home_condition="Brackish water laps the floor.",
        faction_id="saltmere_reeve",
        faction_name="The Reeve",
        faction_stance="extractive",
        faction_notes="Collects in eels or labor.",
        default_scene_problem="The reeve wades toward the door.",
        default_scene_objective="Keep the house one more tide.",
        clocks=clocks,
    )


def _cartridge(clocks: list[dict]) -> WorldCartridge:
    return WorldCartridge.model_validate({
        "cartridge_version": 1,
        "world_id": "saltmere-test",
        "generated_by": "test",
        "source_hash": "deadbeef",
        "archetypes": ["light"],
        "settlement": "Saltmere",
        "settlement_type": "drowned hamlet",
        "region": "the Fens",
        "social_class": "eel-trappers",
        "active_situation": "The tide came early and took the south huts.",
        "world_facts": ["Salt rots the timber", "Eels run on the dark moon", "The reeve keeps a ledger"],
        "family": [{"name": "Gran", "role": "grandmother", "trait": "silent"}],
        "home_location": {"id": "saltmere_house", "name": "The stilt-house", "kind": "hovel", "condition": "Brackish."},
        "faction": {"id": "saltmere_reeve", "name": "The Reeve", "stance": "extractive", "notes": "No mercy."},
        "scene_problem": "The reeve's man wades toward the door.",
        "scene_objective": "Keep the house one more tide.",
        "clocks": clocks,
    })


def _state(turn: int) -> ThreadState:
    return ThreadState(session=SessionData(turn_count=turn))


# ---------------------------------------------------------------------------
# Round-trip: cartridge clocks reach the runtime WorldSeed
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_to_world_seed_carries_clocks(self):
        cart = _cartridge([
            {"label": "The tide rises", "max_segments": 4, "stakes": "the huts drown"},
            {"label": "Rent comes due", "max_segments": 6, "stakes": "the reeve evicts",
             "resolution_hint": "pay in eels", "lethal": True},
        ])
        seed = cart.to_world_seed()
        assert len(seed.clocks) == 2
        assert seed.clocks[0].label == "The tide rises"
        assert seed.clocks[0].lethal is False
        assert seed.clocks[1].lethal is True and seed.clocks[1].max_segments == 6
        assert seed.clocks[1].resolution_hint == "pay in eels"

    def test_clockless_cartridge_yields_empty_clocks(self):
        # The keystone path: builtins ship clocks:[] and must stay clockless.
        cart = _cartridge([])
        assert cart.to_world_seed().clocks == []


# ---------------------------------------------------------------------------
# bootstrap_canon instantiates authored clocks (and only synthesizes the
# single fallback when none are authored)
# ---------------------------------------------------------------------------

class TestInstantiation:
    def test_authored_clocks_become_live_ticking_clocks(self):
        canon = bootstrap_canon(_seed([
            SeedClock(label="The tide rises", max_segments=4, stakes="the huts drown"),
            SeedClock(label="Rent comes due", max_segments=3, stakes="the reeve evicts"),
        ]), "Aria", "girl")
        assert len(canon.clocks) == 2
        # every authored clock is registered AND active (else it never ticks)
        assert set(canon.current_scene.active_clock_ids) == set(canon.clocks.keys())
        assert {c.label for c in canon.clocks.values()} == {"The tide rises", "Rent comes due"}

    def test_no_authored_clocks_synthesizes_single_fallback(self):
        canon = bootstrap_canon(_seed([]), "Aria", "girl")
        assert len(canon.clocks) == 1
        only_id = next(iter(canon.clocks))
        assert only_id.endswith("_pressure")
        assert canon.current_scene.active_clock_ids == [only_id]


# ---------------------------------------------------------------------------
# WB-C4 — the loader is the security boundary, even bypassing the autonovel gate
# ---------------------------------------------------------------------------

class TestLethalityRails:
    def test_at_most_one_lethal_clock_survives(self):
        # Two valid (>=4-segment) lethal clocks — a cartridge would be gate-rejected
        # (WB-C3), but a hand-dropped WorldSeed bypasses the gate entirely.
        clocks = _instantiate_authored_clocks([
            SeedClock(label="The siege tightens", max_segments=6, stakes="the walls fall", lethal=True),
            SeedClock(label="The fever spreads", max_segments=5, stakes="the camp dies", lethal=True),
        ])
        assert sum(1 for c in clocks.values() if c.lethal) == 1
        assert len(clocks) == 2  # both clocks survive; only the kill flag is capped

    def test_short_lethal_clock_is_delethalized(self):
        # A sub-4-segment lethal clock would be an instant adult kill → de-lethalized.
        clocks = _instantiate_authored_clocks([
            SeedClock(label="Instant ruin", max_segments=2, stakes="x", lethal=True),
        ])
        assert all(not c.lethal for c in clocks.values())
        assert len(clocks) == 1  # keeps its stakes; loses only the kill switch

    def test_rails_apply_through_bootstrap(self):
        canon = bootstrap_canon(_seed([
            SeedClock(label="A", max_segments=6, stakes="x", lethal=True),
            SeedClock(label="B", max_segments=6, stakes="y", lethal=True),
            SeedClock(label="C", max_segments=2, stakes="z", lethal=True),
        ]), "Aria", "girl")
        assert sum(1 for c in canon.clocks.values() if c.lethal) == 1


# ---------------------------------------------------------------------------
# WB-C1 / WB-C2 — the doom guard: a world never gains kill authority
# ---------------------------------------------------------------------------

class TestDoomGuard:
    def test_lethal_clock_is_inert_in_childhood(self):
        st = _state(5)  # childhood
        fired = SceneClock(clock_id="c", label="ruin", progress=4, max_segments=4,
                           stakes="the walls fall", lethal=True)
        assert _doom_from_lethal_clock(st, fired) is False
        assert st.doom.active is False        # a ~9-year-old is never doomed by a clock

    def test_lethal_clock_dooms_in_adulthood_via_staged_doom(self):
        st = _state(_ADULT_START_TURN)  # first adult turn
        fired = SceneClock(clock_id="c", label="ruin", progress=4, max_segments=4,
                           stakes="the walls fall", lethal=True)
        took = _doom_from_lethal_clock(st, fired)
        assert took is True
        assert st.doom.active and st.doom.stage == 1 and st.doom.max_stage == 3
        assert st.doom.escapable is False     # inescapable (lethal clock)
        assert not is_doom_terminal(st)        # WB-C2: staged, NOT an instant sever

    def test_nonlethal_clock_never_dooms(self):
        st = _state(30)
        fired = SceneClock(clock_id="c", label="rent", progress=4, max_segments=4,
                           stakes="the reeve evicts", lethal=False)
        assert _doom_from_lethal_clock(st, fired) is False
        assert st.doom.active is False
