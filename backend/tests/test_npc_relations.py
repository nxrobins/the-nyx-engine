"""World & Character Depth — the witnesses remember.

Proves the relationship memory is deterministic, friction-weighted (goodwill
un-farmable, betrayal monotone + compounding), object-resolved (no bystander
scarring), bounded, and cleanly carved from the consequence economy (bond
grants no mechanical buff; the strike path never scars betrayal).
"""

from __future__ import annotations

import pathlib

import pytest

from app.services import canon as canon_mod
from app.services.canon import (
    EVENT_CAP,
    _SOUR_VALENCE,
    _WARM_BASE,
    _bond_band,
    apply_intervention_dispositions,
    classify_interaction,
    render_npc_interior,
    update_npc_relations,
)
from app.schemas.state import (
    CanonNPC,
    SceneState,
    SessionData,
    ThreadState,
    WorldCanon,
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


# ---------------------------------------------------------------------------
# classify_interaction (E1) — verbs + negation guard
# ---------------------------------------------------------------------------

class TestClassify:
    @pytest.mark.parametrize("action,kind", [
        ("I betray Sera", "betrayed"),
        ("I lie to her", "betrayed"),
        ("I attack the guard", "harmed"),
        ("I threaten him", "coerced"),
        ("I help Sera", "aided"),
        ("I protect my brother", "protected"),
        ("I confide in her", "confided"),
        ("I honor the pledge", "honored"),
        ("I wander the road", "neutral"),
    ])
    def test_verbs(self, action, kind):
        assert classify_interaction(action)[0] == kind

    @pytest.mark.parametrize("action", [
        "I refuse to betray Sera",
        "I will never abandon her",
        "I pretend to help Sera",
        "I did not lie to him",
    ])
    def test_negation_yields_neutral(self, action):
        assert classify_interaction(action)[0] == "neutral"


# ---------------------------------------------------------------------------
# Friction-weighted asymmetry (E2)
# ---------------------------------------------------------------------------

class TestAsymmetry:
    def test_sour_warm_ratio_at_least_four(self):
        assert max(abs(v) for v in _SOUR_VALENCE.values()) / max(_WARM_BASE.values()) >= 4.0

    def test_one_betrayal_outweighs_four_warmings(self):
        sera = _npc("Sera")
        st = _state(sera)
        for _ in range(4):
            update_npc_relations(st, "I help Sera", _Outcome())
        assert sera.bond == pytest.approx(2.0)            # 4 * 0.5
        update_npc_relations(st, "I betray Sera", _Outcome())
        assert sera.bond == pytest.approx(0.0)            # one betrayal (-2) erases four warmings

    def test_warmth_is_unfarmable_ambient(self):
        sera = _npc("Sera")
        st = _state(sera)
        for _ in range(6):
            update_npc_relations(st, "I rest quietly by the fire", _Outcome())  # Sera un-named
        assert sera.bond == 0.0                            # presence-only, no farming
        assert sera.last_seen_turn == 5                    # but last_seen still bumped (E6)
        assert sera.events == []

    def test_warmth_throttled_by_betrayal(self):
        sera = _npc("Sera")
        st = _state(sera)
        update_npc_relations(st, "I betray Sera", _Outcome())     # weight 1.0
        before = sera.bond
        update_npc_relations(st, "I help Sera", _Outcome())
        assert sera.bond - before == pytest.approx(0.5 * (1 - 1.0 / 5))  # 0.4, throttled


# ---------------------------------------------------------------------------
# Object resolution (E3) — only the named NPC is scarred
# ---------------------------------------------------------------------------

class TestObjectResolution:
    def test_only_named_npc_is_scarred(self):
        sera = _npc("Sera", "mother")
        aldric = _npc("Aldric", "father")
        sibling = _npc("Cael", "brother")
        st = _state(sera, aldric, sibling)
        update_npc_relations(st, "I lie to my father", _Outcome())
        assert aldric.bond < 0 and aldric.betrayal_count == 1   # father (role) named
        assert sera.bond == 0.0 and sera.betrayal_weight == 0.0
        assert sibling.bond == 0.0 and sibling.betrayal_weight == 0.0

    def test_shelter_everyone_farms_nothing(self):
        sera, aldric = _npc("Sera"), _npc("Aldric", "father")
        st = _state(sera, aldric)
        update_npc_relations(st, "I shelter everyone in the village", _Outcome())
        assert sera.bond == 0.0 and aldric.bond == 0.0


# ---------------------------------------------------------------------------
# Monotone, compounding betrayal through ring eviction (E6)
# ---------------------------------------------------------------------------

class TestBetrayalMonotone:
    def test_count_survives_ring_eviction_and_compounds(self):
        sera = _npc("Sera")
        st = _state(sera)
        weights = []
        for i in range(3):
            update_npc_relations(st, "I betray Sera", _Outcome())
            weights.append(sera.betrayal_weight)
        for _ in range(10):                                # evict early betrayed rows from the ring
            update_npc_relations(st, "I help Sera", _Outcome())
        update_npc_relations(st, "I betray Sera", _Outcome())
        weights.append(sera.betrayal_weight)
        assert sera.betrayal_count == 4                    # dedicated integer, not ring-derived
        assert len(sera.events) <= EVENT_CAP
        # fewer than 4 'betrayed' rows survive the 6-slot ring, proving count != ring
        assert sum(1 for e in sera.events if e.kind == "betrayed") < 4
        assert weights == sorted(weights)                  # monotone non-decreasing

    def test_betrayal_weight_never_decremented_by_warmth(self):
        sera = _npc("Sera")
        st = _state(sera)
        update_npc_relations(st, "I betray Sera", _Outcome())
        w = sera.betrayal_weight
        for _ in range(20):
            update_npc_relations(st, "I help Sera", _Outcome())
        assert sera.betrayal_weight == w                   # no make-up path clears the scar


# ---------------------------------------------------------------------------
# Bounded state (E4)
# ---------------------------------------------------------------------------

class TestBounded:
    def test_ring_capped_and_earliest_scar_survives(self):
        sera = _npc("Sera")
        st = _state(sera)
        update_npc_relations(st, "I betray Sera", _Outcome())   # the scar
        scar_note = sera.events[0].note
        for _ in range(50):
            update_npc_relations(st, "I help Sera", _Outcome())
        assert len(sera.events) <= EVENT_CAP
        assert any(e.note == scar_note for e in sera.events)    # earliest scar pinned
        assert all(len(e.note) <= 80 for e in sera.events)


# ---------------------------------------------------------------------------
# Clean carve (E5/E8) — consequence economy never scars betrayal; no buff
# ---------------------------------------------------------------------------

class TestCarve:
    def test_disposition_strike_never_writes_betrayal(self):
        sera = _npc("Sera", trust=1.0)
        st = _state(sera)
        note = apply_intervention_dispositions(st, kind="oath_broken")
        assert note                                          # it did move trust/fear
        assert sera.betrayal_weight == 0.0 and sera.betrayal_count == 0
        assert sera.bond == 0.0 and sera.events == []        # the betrayal axis is untouched

    def test_bond_grants_no_mechanical_buff(self):
        sera = _npc("Sera", bond=9.0)
        st = _state(sera)
        before = (
            st.soul_ledger.vectors.model_dump(),
            st.pressures.model_dump(),
            st.doom.model_dump(),
        )
        update_npc_relations(st, "I help Sera", _Outcome())
        after = (
            st.soul_ledger.vectors.model_dump(),
            st.pressures.model_dump(),
            st.doom.model_dump(),
        )
        assert before == after                               # completion-as-tragedy, not reward


# ---------------------------------------------------------------------------
# Determinism + rendering
# ---------------------------------------------------------------------------

class TestDeterminismAndRender:
    def test_relationship_layer_is_pure(self):
        src = pathlib.Path(canon_mod.__file__).read_text("utf-8")
        assert "async def" not in src      # no async anywhere in canon
        assert "import random" not in src and "random." not in src
        assert "llm" not in src            # no model call

    def test_same_action_twice_is_byte_identical(self):
        a, b = _npc("Sera"), _npc("Sera")
        sa, sb = _state(a), _state(b)
        update_npc_relations(sa, "I betray Sera", _Outcome())
        update_npc_relations(sb, "I betray Sera", _Outcome())
        assert a.model_dump() == b.model_dump()

    def test_bond_bands(self):
        assert _bond_band(-7) == "will not forgive you"
        assert _bond_band(0) == "guarded"
        assert _bond_band(8) == "would die for you"

    def test_interior_renders_want_and_memory(self):
        sera = _npc("Sera", want="to keep the light", bond=-3.0)
        st = _state(sera)
        update_npc_relations(st, "I betray Sera", _Outcome())
        gloss = render_npc_interior(sera)
        assert "Sera" in gloss and "wants to keep the light" in gloss
        assert "remembers:" in gloss


# ---------------------------------------------------------------------------
# Kernel end-to-end wiring
# ---------------------------------------------------------------------------

class TestKernelWiring:
    @pytest.mark.asyncio
    async def test_betraying_a_present_npc_sours_the_bond(self):
        from app.core.kernel import NyxKernel
        kernel = NyxKernel()
        await kernel.initialize(
            hamartia="Hubris of the Intellect", player_id="depth_test",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",  # Thornwell: Sera present
        )
        result = await kernel.process_turn("I betray Sera")
        assert not result.terminal
        sera = result.state.canon.npcs["npc_sera"]
        assert sera.bond < 0.0
        assert sera.betrayal_count == 1
        assert any(e.kind == "betrayed" for e in sera.events)
