"""Commitment 5 (the thread remembers) — ThreadState survives serialization.

Durability rehydrates a living thread from `ThreadState.model_dump_json()` (and
the Scribe's accumulated `Chapter` list). If any field fails to round-trip, a
resumed life is subtly WRONG — the narrative-incoherence the design exists to
prevent (audit H4/H2; SC-5/CF-6 in the durability plan). This pins round-trip
totality under generation, so a future field with a non-serializable type fails
the build instead of silently corrupting a resumed thread.

Guarantees:
  1. A generated ThreadState round-trips (>=500 examples in CI).
  2. The Scribe's Chapter list round-trips (SC-1 — the book lives outside
     ThreadState and must persist too; note `covers_turns` is a tuple).
  3. A coverage guard: a hand-built maximal state sets EVERY top-level field to a
     non-default value, so a newly-added field can't silently escape guarantee 1.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.book import Chapter
from app.schemas.morpheus import Promise
from app.schemas.vignette import BoundVignette, ConsequencePacket, VignetteChoice
from app.schemas.state import (
    AgentProposal,
    ArrivalCondition,
    CanonFaction,
    CanonLocation,
    CanonNPC,
    DeliberationTrace,
    DoomState,
    HamartiaProfile,
    LegacyEcho,
    NPCEvent,
    Oath,
    OathTerms,
    PressureState,
    SceneClock,
    SceneState,
    SessionData,
    SoulLedger,
    SoulVectors,
    TheLoom,
    ThreadState,
    WorldCanon,
)

# ── leaf strategies (JSON-safe: no NaN/inf, no lone surrogates) ──────────────
_text = st.text(st.characters(blacklist_categories=("Cs",)), max_size=40)
_score = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_signed = st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_ids = st.from_regex(r"[a-z0-9][a-z0-9_-]{2,12}", fullmatch=True)

# dict[str, object] (scene_patch) — only JSON-native values, else round-trip is
# undefined by design. Kept shallow; that is the contract the engine honors.
_json_leaf = st.none() | st.booleans() | st.integers(-999, 999) | _signed | _text
_json_val = st.recursive(
    _json_leaf,
    lambda c: st.lists(c, max_size=3) | st.dictionaries(_text, c, max_size=3),
    max_leaves=6,
)
_json_obj = st.dictionaries(_text, _json_val, max_size=4)


def _m(cls, **fields):
    return st.builds(cls, **fields)


_vectors = _m(SoulVectors, metis=_score, bia=_score, kleos=_score, aidos=_score)
_terms = _m(
    OathTerms, subject=_text, promised_action=_text,
    protected_target=st.none() | _text, forbidden_action=st.none() | _text,
    deadline=st.none() | _text, witness=st.none() | _text, price=st.none() | _text,
)
_oath = _m(
    Oath, oath_id=_ids, text=_text, turn_sworn=st.integers(1, 60),
    broken=st.booleans(), terms=st.none() | _terms,
    status=st.sampled_from(["active", "fulfilled", "broken", "transformed"]),
    fulfillment_note=_text,
)
_hamartia = _m(
    HamartiaProfile, name=_text, choice_bias=_text, nemesis_multiplier=_score,
    eris_bias=_signed, style_directive=_text, refusal_pattern=_text, social_cost_bias=_text,
)
_npc_event = _m(
    NPCEvent, turn=st.integers(0, 60),
    kind=st.sampled_from(["betrayed", "harmed", "aided", "protected", "neutral"]),
    valence=st.floats(-2.0, 2.0, allow_nan=False, allow_infinity=False), note=_text,
)
_arrival = _m(
    ArrivalCondition, min_turn=st.integers(0, 200), requires_bond_npc_id=st.just(""),
    requires_bond_at_least=_signed, on_clock_resolved=st.just(""),
    arrival_priority=st.integers(0, 99),
)
_npc = _m(
    CanonNPC, npc_id=_ids, name=_text, role=_text, home_location_id=_ids,
    current_location_id=_ids,
    status=st.sampled_from(["alive", "dead", "missing", "departed", "latent"]),
    trust=_signed, fear=_signed, obligation=_signed, tags=st.lists(_text, max_size=3),
    last_seen_turn=st.integers(0, 60), departed_turn=st.integers(0, 60),
    died_turn=st.integers(0, 60), want=_text,
    bond=_signed, betrayal_weight=_score, betrayal_count=st.integers(0, 99),
    events=st.lists(_npc_event, max_size=3),
    arrival_condition=st.none() | _arrival, arrived_turn=st.integers(0, 60),
)
_location = _m(
    CanonLocation, location_id=_ids, name=_text, region=_text, kind=_text,
    current_condition=_text, tags=st.lists(_text, max_size=3),
)
_faction = _m(
    CanonFaction, faction_id=_ids, name=_text, stance=_text,
    leverage=_signed, hostility=_signed, notes=_text,
)
_clock = _m(
    SceneClock, clock_id=_ids, label=_text, progress=st.integers(0, 4),
    max_segments=st.integers(1, 8), stakes=_text, resolution_hint=_text,
    lethal=st.booleans(), claims_npc_id=st.just(""),
)
_scene = _m(
    SceneState, scene_id=_ids, location_id=_ids,
    present_npc_ids=st.lists(_ids, max_size=3), active_clock_ids=st.lists(_ids, max_size=3),
    immediate_problem=_text, scene_objective=_text, carryover_consequence=_text,
)
_canon = _m(
    WorldCanon,
    npcs=st.dictionaries(_ids, _npc, max_size=3),
    locations=st.dictionaries(_ids, _location, max_size=2),
    factions=st.dictionaries(_ids, _faction, max_size=2),
    clocks=st.dictionaries(_ids, _clock, max_size=2),
    current_scene=st.none() | _scene, world_facts=st.lists(_text, max_size=3),
)
_proposal = _m(
    AgentProposal, agent=_text, allow_action=st.booleans(), refusal_reason=_text,
    scene_patch=_json_obj, vector_patch=st.dictionaries(_text, _signed, max_size=4),
    pressure_patch=st.dictionaries(_text, _signed, max_size=4), prophecy_patch=_text,
    death_flag=st.booleans(), death_reason=_text, intervention_copy=_text,
    priority_note=_text, confidence=_score,
)
_trace = _m(
    DeliberationTrace, turn_number=st.integers(1, 60),
    proposals=st.lists(_proposal, max_size=3), winner_order=st.lists(_text, max_size=4),
    final_reason=_text,
)
_doom = _m(
    DoomState, active=st.booleans(),
    cause=st.sampled_from(["", "broken_oath", "wounds", "faction_heat", "clock", "old_age"]),
    description=_text, stage=st.integers(0, 3), max_stage=st.integers(1, 3),
    started_turn=st.integers(0, 60), escapable=st.booleans(), escape_hint=_text,
)
_legacy = _m(
    LegacyEcho, source_thread_id=_ids, epitaph=_text, hamartia=_text,
    inherited_mark=_text, mechanical_effect=_text,
)
_pressures = _m(
    PressureState, suspicion=_signed, scarcity=_signed, wounds=_signed, debt=_signed,
    faction_heat=_signed, omen=_signed, exploit_score=_signed,
    stability_streak=st.integers(0, 60),
)
_session = _m(
    SessionData, player_id=_ids, player_name=_text, player_gender=_text,
    first_memory=_text, turn_count=st.integers(0, 60), run_number=st.integers(1, 9),
    current_environment=_text, epoch_phase=st.integers(1, 4),
    ui_mode=st.sampled_from(["buttons", "open"]), player_age=st.integers(3, 80),
    beat_position=st.sampled_from(["SETUP", "COMPLICATION", "RESOLUTION", "OPEN"]),
    chapter_index=st.integers(0, 40), beats_spent=st.integers(0, 5),
    beat_kind=st.sampled_from(["", "vignette", "crucible"]),
)
_ledger = _m(
    SoulLedger, hamartia=_text, hamartia_profile=st.none() | _hamartia,
    vectors=_vectors, active_oaths=st.lists(_oath, max_size=3),
)
_loom = _m(
    TheLoom, current_prophecy=_text, milestone_reached=st.booleans(),
    image_prompt_trigger=_text,
)


@st.composite
def _promises(draw):
    event_turn = draw(st.integers(1, 40))
    window = draw(st.integers(1, 10))
    return Promise(
        promise_id=draw(_ids),
        description=draw(st.text(st.characters(blacklist_categories=("Cs",)), min_size=10, max_size=60)),
        event_turn=event_turn, significance=draw(_text),
        due_turn=event_turn + window,
        status=draw(st.sampled_from(["planted", "promoted", "paid", "abandoned"])),
        paid_turn=draw(st.integers(0, event_turn + window)),
    )


@st.composite
def _chapters(draw):
    start = draw(st.integers(1, 20))
    end = draw(st.integers(start, start + 5))
    based_on = draw(st.integers(end, end + 5))
    return Chapter(
        epoch_index=draw(st.integers(1, 6)),
        title=draw(st.text(st.characters(blacklist_categories=("Cs",)), min_size=3, max_size=60)),
        covers_turns=(start, end),
        prose=draw(st.text(st.characters(blacklist_categories=("Cs",)), min_size=100, max_size=180)),
        thread_stamp=draw(_ids), based_on_turn=based_on,
    )


_thread_states = _m(
    ThreadState,
    session=_session, soul_ledger=_ledger, the_loom=_loom, pressures=_pressures,
    canon=st.none() | _canon, doom=_doom, rag_context=st.lists(_text, max_size=4),
    world_context=_text, last_action=_text, last_outcome=_text,
    terminal=st.booleans(), death_reason=_text, current_dream=_text,
    craft_notes=st.lists(_text, max_size=3), ledger=st.lists(_promises(), max_size=3),
    used_vignette_ids=st.lists(_ids, max_size=4),
    pending_vignette=st.none() | _m(
        BoundVignette, vignette_id=_ids, situation=_text,
        choices=st.lists(
            _m(VignetteChoice,
               label=st.text(st.characters(blacklist_categories=("Cs",)), min_size=3, max_size=40),
               packet=st.builds(ConsequencePacket, vector_deltas=st.just({"bia": 0.5}))),
            min_size=1, max_size=3,
        ),
        cast_names=st.dictionaries(_ids, _text, max_size=2),
    ),
    life_voice=_text, world_id=_text, prose_history=st.lists(_text, max_size=4),
    chronicle=st.lists(_text, max_size=4), factual_chronicle=st.lists(_text, max_size=4),
    recent_traces=st.lists(_trace, max_size=3), legacy_echoes=st.lists(_legacy, max_size=2),
)


def _roundtrip(model):
    return type(model).model_validate_json(model.model_dump_json())


@settings(max_examples=500)
@given(_thread_states)
def test_thread_state_round_trips(state):
    assert _roundtrip(state) == state


@given(st.lists(_chapters(), max_size=4))
def test_chapter_list_round_trips(chapters):
    # The Scribe's book lives outside ThreadState (SC-1). covers_turns is a tuple
    # — the classic JSON-array-vs-tuple trap.
    import json

    dumped = json.dumps([c.model_dump(mode="json") for c in chapters])
    restored = [Chapter.model_validate(d) for d in json.loads(dumped)]
    assert restored == chapters
    for c in restored:
        assert isinstance(c.covers_turns, tuple)


def _maximal_thread_state() -> ThreadState:
    """Every top-level field set to a non-default, valid value."""
    npc = CanonNPC(
        npc_id="npc_sera", name="Sera", role="mother", home_location_id="loc_home",
        current_location_id="loc_home", status="alive", trust=2.0, bond=1.5,
        want="to keep her child safe", events=[NPCEvent(turn=3, kind="aided", note="shared bread")],
    )
    canon = WorldCanon(
        npcs={"npc_sera": npc},
        locations={"loc_home": CanonLocation(location_id="loc_home", name="Home", region="Ashlands", kind="house")},
        factions={"fac_v": CanonFaction(faction_id="fac_v", name="House Voss", hostility=1.0)},
        clocks={"clk": SceneClock(clock_id="clk", label="the road closes", lethal=True)},
        current_scene=SceneState(scene_id="sc1", location_id="loc_home", immediate_problem="a knock at the door"),
        world_facts=["The Ashlands are volcanic, not burned."],
    )
    return ThreadState(
        session=SessionData(
            player_id="p1", player_name="Hero", turn_count=12, player_age=14,
            epoch_phase=3, chapter_index=4, beats_spent=2, beat_kind="vignette",
        ),
        soul_ledger=SoulLedger(
            hamartia="Wrath",
            hamartia_profile=HamartiaProfile(name="Wrath", choice_bias="violent", style_directive="burns hot"),
            vectors=SoulVectors(metis=6.0, bia=8.0, kleos=3.0, aidos=2.0),
            active_oaths=[Oath(oath_id="oath_1", text="I swear to protect Sera", turn_sworn=3)],
        ),
        the_loom=TheLoom(current_prophecy="The fire you carry will consume what you love.", milestone_reached=True),
        pressures=PressureState(suspicion=1.2, wounds=2.0, faction_heat=1.5, omen=0.8, stability_streak=4),
        canon=canon,
        doom=DoomState(active=True, cause="broken_oath", description="a debt claimed", stage=1, escapable=False),
        rag_context=["earlier, the elder warned of the road"],
        world_context="=== THE ORIGIN ===\nThornwell, a hill village.",
        last_action="I confront the man at the door",
        last_outcome="violent_triumph",
        terminal=True,
        death_reason="An oath was broken; the thread is already cut.",
        current_dream="a river of ash",
        craft_notes=["do not name the dead as present"],
        ledger=[Promise(promise_id="a_debt", description="the father who never returned", event_turn=2, due_turn=10)],
        used_vignette_ids=["thornwell_wall_stone"],
        pending_vignette=BoundVignette(
            vignette_id="thornwell_tallow_short",
            situation="The autumn render comes up short. Sera recounts the barrels.",
            choices=[VignetteChoice(
                label="Lean on the tallow supplier",
                packet=ConsequencePacket(vector_deltas={"bia": 0.7}),
            )],
            cast_names={"mother": "Sera"},
        ),
        life_voice="clipped, wrathful",
        world_id="builtin-stone",
        prose_history=["The door shuddered.", "Sera's hand found your shoulder."],
        chronicle=["A child of ash learned the weight of a vow."],
        factual_chronicle=["Turn 3: Sera aided the child."],
        recent_traces=[DeliberationTrace(turn_number=12, winner_order=["lachesis", "nemesis"], final_reason="Nemesis intervened.")],
        legacy_echoes=[LegacyEcho(source_thread_id="p1:run-0", epitaph="He burned bright.", hamartia="Wrath", inherited_mark="the ash-mark", mechanical_effect="+omen at birth")],
    )


def test_maximal_state_round_trips():
    s = _maximal_thread_state()
    assert _roundtrip(s) == s


def test_maximal_covers_every_top_level_field():
    """Coverage guard: a newly-added ThreadState field left at its default here
    fails loudly, naming the field — so it can't silently escape the round-trip
    property above."""
    s = _maximal_thread_state()
    defaults = ThreadState()
    unexercised = [
        name for name in ThreadState.model_fields
        if getattr(s, name) == getattr(defaults, name)
    ]
    assert not unexercised, (
        f"_maximal_thread_state leaves these fields at their default "
        f"(untested for serialization): {unexercised}"
    )
