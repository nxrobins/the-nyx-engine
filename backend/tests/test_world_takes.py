"""The World Takes — a fired clock claims a named NPC's life, under deterministic law.

The world can take someone you love, but only a NAMED, VISIBLE, ANSWERABLE threat:
ticking across turns, advancing only on the player's own provocations, and pushable
back by protecting the target (relieve_clock). Never a model's choice, never the
player's death, never an un-earned strike. The loss is remembered, never erased.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.schemas.cartridge import WorldCartridge
from app.schemas.state import (
    CanonNPC,
    SceneClock,
    SceneState,
    SessionData,
    ThreadState,
    WorldCanon,
)
from app.services.canon import (
    _alive_present_ids,
    _claim_npc,
    relieve_clock,
    tick_scene_clocks,
)


# ── builders ────────────────────────────────────────────────────────────────

def _npc(name: str, role: str = "friend", *, last_seen_turn: int = 1, **kw) -> CanonNPC:
    return CanonNPC(
        npc_id=f"npc_{name.lower()}", name=name, role=role,
        home_location_id="home", current_location_id="home",
        last_seen_turn=last_seen_turn, **kw,
    )


def _claiming_clock(target: str, *, progress: int = 3, max_segments: int = 4) -> SceneClock:
    return SceneClock(
        clock_id="clock_fever", label="The Fever", progress=progress,
        max_segments=max_segments, stakes="the fever spreads through the low quarter",
        claims_npc_id=f"npc_{target.lower()}",
    )


def _state(*npcs: CanonNPC, clock: SceneClock | None = None, turn: int = 15,
           stability_streak: int = 0) -> ThreadState:
    clocks = {clock.clock_id: clock} if clock else {}
    scene = SceneState(
        scene_id="s", location_id="home",
        present_npc_ids=[n.npc_id for n in npcs],
        active_clock_ids=[clock.clock_id] if clock else [],
    )
    st = ThreadState(
        session=SessionData(turn_count=turn),
        canon=WorldCanon(npcs={n.npc_id: n for n in npcs}, current_scene=scene, clocks=clocks),
    )
    st.pressures.stability_streak = stability_streak
    return st


# ── the kill ────────────────────────────────────────────────────────────────

class TestClaimNpc:
    def test_takes_an_alive_met_adult_target(self):
        sera, kael = _npc("Sera"), _npc("Kael", "father")
        st = _state(sera, kael, clock=_claiming_clock("Sera"))
        note = _claim_npc(st, st.canon.clocks["clock_fever"])
        assert sera.status == "dead"
        assert note and "Sera" in note
        assert "npc_sera" not in st.canon.current_scene.present_npc_ids   # re-settled (NC-4)
        assert any(e.kind == "lost" for e in sera.events)                # remembered (NC-10)
        assert "npc_sera" in st.canon.npcs                               # not erased

    def test_never_re_kills_a_dead_or_departed_target(self):
        for status in ("dead", "departed", "missing"):
            sera = _npc("Sera", status=status)
            other = _npc("Kael", "father")
            st = _state(sera, other, clock=_claiming_clock("Sera"))
            assert _claim_npc(st, st.canon.clocks["clock_fever"]) is None

    def test_spares_an_unmet_target(self):
        # A death with no grief is cheap, not tragic (NC-8).
        sera = _npc("Sera", last_seen_turn=0)
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera"))
        assert _claim_npc(st, st.canon.clocks["clock_fever"]) is None
        assert sera.status == "alive"

    def test_spares_childhood(self):
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera"), turn=6)
        assert _claim_npc(st, st.canon.clocks["clock_fever"]) is None   # NC-5b
        assert sera.status == "alive"

    def test_never_empties_the_living_cast(self):
        sera = _npc("Sera")   # the only living soul
        st = _state(sera, clock=_claiming_clock("Sera"))
        assert _claim_npc(st, st.canon.clocks["clock_fever"]) is None   # NC-9
        assert sera.status == "alive"

    def test_never_touches_player_terminality(self):
        # NC-2: the claim writes NPC status only; no doom/terminal anywhere.
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera"))
        _claim_npc(st, st.canon.clocks["clock_fever"])
        assert not st.doom.active


# ── agency ──────────────────────────────────────────────────────────────────

class TestRelieveClock:
    def test_protecting_the_named_target_buys_time(self):
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera", progress=3))
        notes = relieve_clock(st, "I shield Sera from the worst of it")
        assert st.canon.clocks["clock_fever"].progress == 2
        assert notes and "Sera" in notes[0]

    def test_floors_at_zero(self):
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera", progress=0))
        relieve_clock(st, "I protect Sera")
        assert st.canon.clocks["clock_fever"].progress == 0

    def test_a_non_protecting_action_does_nothing(self):
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"), clock=_claiming_clock("Sera", progress=3))
        assert relieve_clock(st, "I attack Sera") == []
        assert st.canon.clocks["clock_fever"].progress == 3

    def test_protecting_someone_else_does_not_help(self):
        sera, kael = _npc("Sera"), _npc("Kael", "father")
        st = _state(sera, kael, clock=_claiming_clock("Sera", progress=3))
        assert relieve_clock(st, "I protect Kael") == []
        assert st.canon.clocks["clock_fever"].progress == 3


# ── the tick: player-coupled advance + claim on fire ──────────────────────────

class TestTickClaims:
    def test_claim_advances_on_player_provocation_and_fires(self):
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"),
                    clock=_claiming_clock("Sera", progress=3, max_segments=4))
        tick = tick_scene_clocks(st, intervention_struck=True, resolution_beat=False)
        assert sera.status == "dead"
        assert "Sera" in tick.claimed
        # note order: the stakes note precedes the death note (NC test stability)
        assert len(tick.notes) == 2 and "Sera" in tick.notes[1]

    def test_claim_does_not_advance_on_scheduler_only_ticks(self):
        # A RESOLUTION beat + coasting (no provocation) must NOT advance a claim (NC-5c).
        sera = _npc("Sera")
        st = _state(sera, _npc("Kael", "father"),
                    clock=_claiming_clock("Sera", progress=3, max_segments=4),
                    stability_streak=5)
        tick = tick_scene_clocks(st, intervention_struck=False, resolution_beat=True)
        assert sera.status == "alive"
        assert st.canon.clocks["clock_fever"].progress == 3
        assert tick.claimed == []

    def test_non_claiming_clock_is_unchanged_old_single_note(self):
        # Builtin regression lock: a plain clock fires with exactly the old note.
        plain = SceneClock(clock_id="clock_rent", label="Rent", progress=3,
                           max_segments=4, stakes="the lord seizes the kiln")
        st = _state(_npc("Sera"), clock=plain)
        tick = tick_scene_clocks(st, intervention_struck=True, resolution_beat=True)
        assert tick.claimed == []
        assert len(tick.notes) == 1 and "Rent" in tick.notes[0]


# ── authoring-time integrity (the cartridge validator) ────────────────────────

def _payload(**overrides) -> dict:
    p = {
        "cartridge_version": 1, "world_id": "test-world", "generated_by": "test",
        "source_hash": "abc123", "archetypes": ["light"], "settlement": "Testholm",
        "settlement_type": "village", "region": "the Testlands", "social_class": "potters",
        "active_situation": "The kiln has gone cold and the winter rent is due.",
        "world_facts": ["A river runs east", "The lord is absent", "Clay is wealth"],
        "family": [{"name": "Mara", "role": "mother", "trait": "weary"}],
        "home_location": {"id": "kiln", "name": "The kiln", "kind": "workshop",
                          "condition": "Ash and unfired pots."},
        "faction": {"id": "guild", "name": "Potters' Guild", "stance": "wary",
                    "notes": "They control the clay pits."},
        "scene_problem": "The rent collector is at the door.",
        "scene_objective": "Keep the pitch through winter.",
    }
    p.update(overrides)
    return p


def _clock(**kw) -> dict:
    base = {"label": "The Fever", "max_segments": 4, "stakes": "the fever takes the weak"}
    base.update(kw)
    return base


class TestCartridgeValidator:
    def test_claim_by_name_resolves_to_canonical_id(self):
        cart = WorldCartridge.model_validate(_payload(clocks=[_clock(claims_npc_id="Mara")]))
        assert cart.clocks[0].claims_npc_id == "npc_mara"   # NC-6 canonical form stored

    def test_claim_by_id_is_accepted(self):
        cart = WorldCartridge.model_validate(_payload(clocks=[_clock(claims_npc_id="npc_mara")]))
        assert cart.clocks[0].claims_npc_id == "npc_mara"

    def test_dangling_claim_is_rejected(self):
        with pytest.raises(ValueError):   # NC-6 — author's tragedy would silently never fire
            WorldCartridge.model_validate(_payload(clocks=[_clock(claims_npc_id="Ghost")]))

    def test_lethal_and_claiming_is_rejected(self):
        with pytest.raises(ValueError):   # NC-7 — threaten the player OR take someone, never both
            WorldCartridge.model_validate(
                _payload(clocks=[_clock(lethal=True, claims_npc_id="Mara")])
            )

    def test_no_claim_is_a_pure_passthrough(self):
        cart = WorldCartridge.model_validate(_payload(clocks=[_clock()]))
        assert cart.clocks[0].claims_npc_id == ""
        assert cart.to_world_seed().clocks[0].claims_npc_id == ""   # rides into the seed


# ── end to end, through the live kernel ──────────────────────────────────────

class TestKernelIntegration:
    @pytest.mark.asyncio
    async def test_a_claim_lands_through_a_real_turn(self, monkeypatch):
        import app.agents.eris as eris_module
        monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)  # no chaos noise

        k = NyxKernel()
        await k.initialize(
            hamartia="Hubris of the Intellect", player_id="takes",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        # World-agnostic: inject a met, living target + a claiming clock one tick from
        # firing, in an adult turn. (Which seed was selected doesn't matter here.)
        sera = _npc("Sera")
        k.state.canon.npcs["npc_sera"] = sera
        k.state.canon.current_scene.present_npc_ids.append("npc_sera")
        k.state.session.turn_count = 16
        k.state.canon.clocks["clock_fever"] = _claiming_clock("Sera", progress=3, max_segments=4)
        k.state.canon.current_scene.active_clock_ids.append("clock_fever")
        # Provoke the Fates so the claiming clock advances (player-coupled tick): a high
        # exploit score reliably draws a Nemesis punishment in mock mode → intervention.
        k.state.pressures.exploit_score = 3.0

        result = await k.process_turn("I work the same swindle on the magistrate again")
        assert not result.terminal                                   # the PLAYER does not die (NC-2)
        assert k.state.canon.npcs["npc_sera"].status == "dead"       # the world took Sera
        assert "npc_sera" not in k.state.canon.current_scene.present_npc_ids
