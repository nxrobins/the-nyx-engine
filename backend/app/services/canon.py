"""Canonical world state helpers.

Phase 1 keeps the world model deliberately small: named people, named places,
one active scene, and a simple unresolved clock. This is enough to ground the
turn loop without turning Nyx into a full simulation sandbox.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.world_seeds import WorldSeed
from app.schemas.state import (
    CanonFaction,
    CanonLocation,
    CanonNPC,
    NPCEvent,
    SceneClock,
    SceneState,
    ThreadState,
    WorldCanon,
)


def _slug(value: str) -> str:
    """Return a stable lowercase slug for ids."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def _clock_label(seed: WorldSeed) -> str:
    text = seed.default_scene_problem or seed.active_situation
    text = text.strip()
    if len(text) <= 72:
        return text
    clipped = text[:69].rstrip(" ,.;:")
    return clipped + "..."


def _alive_present_ids(canon: WorldCanon, npc_ids: list[str]) -> list[str]:
    """Filter present ids so dead or missing NPCs do not remain in-scene."""
    alive_ids: list[str] = []
    for npc_id in npc_ids:
        npc = canon.npcs.get(npc_id)
        if npc and npc.status == "alive":
            alive_ids.append(npc_id)
    return alive_ids


def bootstrap_canon(seed: WorldSeed, player_name: str, player_gender: str) -> WorldCanon:
    """Build the initial canonical world state from a world seed."""
    settlement_id = f"settlement_{_slug(seed.settlement)}"
    home_id = seed.home_location_id
    clock_id = f"clock_{_slug(seed.settlement)}_pressure"

    locations = {
        settlement_id: CanonLocation(
            location_id=settlement_id,
            name=seed.settlement,
            region=seed.region,
            kind=seed.settlement_type,
            current_condition=seed.active_situation,
            tags=["settlement", _slug(seed.settlement_type)],
        ),
        home_id: CanonLocation(
            location_id=home_id,
            name=seed.home_location_name,
            region=seed.settlement,
            kind=seed.home_location_kind,
            current_condition=seed.home_condition,
            tags=["home", "origin"],
        ),
    }

    npcs: dict[str, CanonNPC] = {}
    present_npc_ids: list[str] = []
    for npc in seed.family:
        npc_id = f"npc_{_slug(npc.name)}"
        npcs[npc_id] = CanonNPC(
            npc_id=npc_id,
            name=npc.name,
            role=npc.role,
            home_location_id=home_id,
            current_location_id=home_id,
            trust=npc.trust,
            fear=npc.fear,
            obligation=npc.obligation,
            tags=list(npc.tags),
            last_seen_turn=1,
            want=npc_want(npc.name),
        )
        present_npc_ids.append(npc_id)

    factions: dict[str, CanonFaction] = {}
    if seed.faction_id and seed.faction_name:
        factions[seed.faction_id] = CanonFaction(
            faction_id=seed.faction_id,
            name=seed.faction_name,
            stance=seed.faction_stance,
            leverage=0.5,
            hostility=0.2,
            notes=seed.faction_notes,
        )

    clocks = {
        clock_id: SceneClock(
            clock_id=clock_id,
            label=_clock_label(seed),
            progress=0,
            max_segments=4,
            stakes=seed.active_situation,
            resolution_hint=seed.default_scene_objective,
        )
    }

    current_scene = SceneState(
        scene_id="scene_turn_1_birth",
        location_id=home_id,
        present_npc_ids=present_npc_ids,
        active_clock_ids=[clock_id],
        immediate_problem=seed.default_scene_problem or seed.active_situation,
        scene_objective=seed.default_scene_objective,
        carryover_consequence="",
    )

    return WorldCanon(
        npcs=npcs,
        locations=locations,
        factions=factions,
        clocks=clocks,
        current_scene=current_scene,
        world_facts=list(seed.world_facts),
    )


def render_scene_snapshot(state: ThreadState) -> str:
    """Render a compact prompt-friendly snapshot of the active scene."""
    canon = state.canon
    if not canon or not canon.current_scene:
        return ""

    scene = canon.current_scene
    location = canon.locations.get(scene.location_id)
    lines: list[str] = []

    if location:
        lines.append(f"CURRENT LOCATION: {location.name} ({location.kind}, {location.region})")

    present_lines: list[str] = []
    for idx, npc_id in enumerate(_alive_present_ids(canon, scene.present_npc_ids)):
        npc = canon.npcs[npc_id]
        if idx < 3:
            present_lines.append(render_npc_interior(npc))   # full interior for the first few
        else:
            tail = f"{npc.name} ({npc.role})"                 # degrade past the cap
            if npc.want:
                tail += f" (wants {npc.want})"
            present_lines.append(tail)
    if present_lines:
        present_str = " | ".join(present_lines)
        if len(present_str) > 400:                            # hard prompt-budget guard
            present_str = present_str[:397].rstrip() + "..."
        lines.append("PRESENT: " + present_str)

    clocks = []
    for clock_id in scene.active_clock_ids:
        clock = canon.clocks.get(clock_id)
        if clock:
            clocks.append(f"{clock.label} [{clock.progress}/{clock.max_segments}]")
    if clocks:
        lines.append("CLOCKS: " + "; ".join(clocks))

    if scene.immediate_problem:
        lines.append(f"IMMEDIATE PROBLEM: {scene.immediate_problem}")
    if scene.scene_objective:
        lines.append(f"SCENE OBJECTIVE: {scene.scene_objective}")
    if scene.carryover_consequence:
        lines.append(f"CARRYOVER: {scene.carryover_consequence}")

    if canon.world_facts:
        lines.append("WORLD FACTS: " + " | ".join(canon.world_facts[:3]))

    return "\n".join(lines)


def derive_environment_string(state: ThreadState) -> str:
    """Create the UI-facing environment string from canonical state."""
    canon = state.canon
    if not canon or not canon.current_scene:
        return state.session.current_environment

    scene = canon.current_scene
    location = canon.locations.get(scene.location_id)
    if not location:
        return state.session.current_environment

    description = (
        scene.carryover_consequence
        or scene.immediate_problem
        or location.current_condition
    )

    if not description:
        return f"{location.name} ({location.kind}, {location.region})"

    lowered = description.lower()
    if location.name.lower() in lowered:
        return description

    return f"{location.name} ({location.kind}, {location.region}). {description}"


def apply_environment_update(state: ThreadState, environment_update: str) -> None:
    """Fold Lachesis environment output into the current canonical scene."""
    canon = state.canon
    if not environment_update:
        return

    if not canon or not canon.current_scene:
        state.session.current_environment = environment_update
        return

    scene = canon.current_scene
    location = canon.locations.get(scene.location_id)
    if location:
        location.current_condition = environment_update
    scene.carryover_consequence = environment_update
    state.session.current_environment = derive_environment_string(state)


def advance_scene(
    state: ThreadState,
    *,
    location_id: str | None = None,
    present_npc_ids: list[str] | None = None,
    immediate_problem: str | None = None,
    scene_objective: str | None = None,
    carryover_consequence: str | None = None,
) -> None:
    """Advance the canonical scene while preserving the world canon."""
    canon = state.canon
    if not canon or not canon.current_scene:
        return

    current = canon.current_scene
    next_location_id = location_id or current.location_id
    next_present = present_npc_ids if present_npc_ids is not None else current.present_npc_ids
    next_present = _alive_present_ids(canon, next_present)

    for npc_id in next_present:
        npc = canon.npcs.get(npc_id)
        if npc:
            npc.current_location_id = next_location_id
            npc.last_seen_turn = state.session.turn_count

    canon.current_scene = SceneState(
        scene_id=f"scene_turn_{max(state.session.turn_count, 1)}_{_slug(next_location_id)}",
        location_id=next_location_id,
        present_npc_ids=next_present,
        active_clock_ids=list(current.active_clock_ids),
        immediate_problem=immediate_problem if immediate_problem is not None else current.immediate_problem,
        scene_objective=scene_objective if scene_objective is not None else current.scene_objective,
        carryover_consequence=(
            carryover_consequence
            if carryover_consequence is not None
            else current.carryover_consequence
        ),
    )
    state.session.current_environment = derive_environment_string(state)


# ---------------------------------------------------------------------------
# Scene Clocks — the world's problems mature whether or not you attend them
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ClockTickResult:
    """Outcome of one turn of clock evolution."""
    fired: list[SceneClock] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pressure_spike: dict[str, float] = field(default_factory=dict)


def advance_clock(state: ThreadState, clock_id: str, amount: int = 1) -> SceneClock | None:
    """Advance a clock by ``amount`` segments. Returns the clock if it fired."""
    canon = state.canon
    if not canon or amount <= 0:
        return None
    clock = canon.clocks.get(clock_id)
    if clock is None or clock.progress >= clock.max_segments:
        return None
    clock.progress = min(clock.progress + amount, clock.max_segments)
    if clock.progress >= clock.max_segments:
        return clock
    return None


def _fire_clock(state: ThreadState, clock: SceneClock) -> str:
    """Make a filled clock's stakes true in the scene. Returns the note."""
    scene = state.canon.current_scene if state.canon else None
    note = f"The clock '{clock.label}' has run out: {clock.stakes}"
    if scene is not None:
        if clock.clock_id in scene.active_clock_ids:
            scene.active_clock_ids.remove(clock.clock_id)
        scene.carryover_consequence = (
            f"{scene.carryover_consequence}; {note}".strip("; ")
            if scene.carryover_consequence else note
        )
    return note


def tick_scene_clocks(
    state: ThreadState,
    *,
    intervention_struck: bool,
    resolution_beat: bool,
) -> ClockTickResult:
    """Deterministic per-turn clock policy.

    Advancement per active clock (capped at +2 per turn):
      +1 when Nemesis or Eris struck — the Fates accelerate the world's problems
      +1 on RESOLUTION beats — a chapter crisis forces every situation forward
      +1 when the player has coasted (stability_streak >= 3) — ignoring the
         world does not pause it

    A fired clock writes its stakes into the scene as carryover consequence
    and spikes omen/scarcity pressure. Lethal clocks are returned in
    ``fired`` so the kernel can begin a doom.
    """
    result = ClockTickResult()
    canon = state.canon
    if not canon or not canon.current_scene:
        return result

    amount = 0
    if intervention_struck:
        amount += 1
    if resolution_beat:
        amount += 1
    if state.pressures.stability_streak >= 3:
        amount += 1
    amount = min(amount, 2)
    if amount == 0:
        return result

    for clock_id in list(canon.current_scene.active_clock_ids):
        fired = advance_clock(state, clock_id, amount)
        if fired is not None:
            result.fired.append(fired)
            result.notes.append(_fire_clock(state, fired))

    if result.fired:
        result.pressure_spike = {"omen": 0.6, "scarcity": 0.3}

    return result


# ---------------------------------------------------------------------------
# Intervention consequences — the Fates leave marks on people, not just prose
# ---------------------------------------------------------------------------

def _clamp_disposition(value: float) -> float:
    return max(-5.0, min(5.0, value))


def apply_intervention_dispositions(
    state: ThreadState,
    *,
    kind: str,
    severity: float = 1.0,
) -> str:
    """Shift present NPCs' dispositions when a Fate strikes.

    kind: "nemesis" | "eris" | "oath_broken"
    Returns a material-change note naming the witnesses, or "" when no
    living NPC is present to react.
    """
    canon = state.canon
    if not canon or not canon.current_scene:
        return ""

    shifts: dict[str, float]
    faction_hostility = 0.0
    if kind == "oath_broken":
        shifts = {"trust": -1.0, "fear": 0.5}
        faction_hostility = 0.4
        verdict = "saw the oath break"
    elif kind == "nemesis":
        shifts = {"trust": -0.3 * severity, "fear": 0.5 * severity}
        faction_hostility = 0.2
        verdict = "recoil from the judgment"
    elif kind == "eris":
        shifts = {"fear": 0.3 * severity}
        verdict = "flinch at the chaos"
    else:
        return ""

    witnesses: list[str] = []
    for npc_id in canon.current_scene.present_npc_ids:
        npc = canon.npcs.get(npc_id)
        if npc is None or npc.status != "alive":
            continue
        npc.trust = _clamp_disposition(npc.trust + shifts.get("trust", 0.0))
        npc.fear = _clamp_disposition(npc.fear + shifts.get("fear", 0.0))
        witnesses.append(npc.name)

    if faction_hostility > 0.0:
        for faction in canon.factions.values():
            faction.hostility = _clamp_disposition(
                faction.hostility + faction_hostility
            )

    if not witnesses:
        return ""
    return f"Witnesses {verdict}: {', '.join(witnesses)} will remember this."


# ---------------------------------------------------------------------------
# Relationship memory — the present cast remembers what the player did (Depth)
#
# Deterministic, friction-weighted, zero LLM. update_npc_relations is the SOLE
# writer of bond/events/betrayal; apply_intervention_dispositions above moves
# only trust/fear, so the consequence economy is structurally unable to scar
# the betrayal axis (the carve). Souring is cheap; warming is named, committed,
# and throttled by accumulated betrayal; betrayal compounds via a dedicated
# monotone integer the lossy events ring never feeds. bond grants NO mechanical
# buff — its only payload is rendered interiority (completion-as-tragedy).
# ---------------------------------------------------------------------------

EVENT_CAP = 6
_WARM_BASE = {"aided": 0.5, "protected": 0.5, "confided": 0.3, "honored": 0.3}
_SOUR_VALENCE = {"betrayed": -2.0, "harmed": -1.5, "coerced": -1.0}
_SOURING_KINDS = frozenset(_SOUR_VALENCE)

# Ordered keyword table; first token match wins (souring verbs precede warming).
_VERB_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("betrayed", ("betray", "betrayed", "betrays", "abandon", "abandoned", "abandons",
                  "forsake", "forsook", "sell out", "sold out", "rat out", "lie", "lied", "lies")),
    ("harmed", ("kill", "killed", "stab", "stabbed", "strike", "struck", "hit", "beat",
                "burn", "burned", "steal", "stole", "rob", "robbed", "attack", "attacked",
                "maim", "wound", "wounded", "slay", "slew")),
    ("coerced", ("threaten", "threatened", "force", "forced", "blackmail", "coerce",
                 "coerced", "extort", "extorted", "intimidate")),
    ("aided", ("save", "saved", "heal", "healed", "feed", "fed", "shelter", "sheltered",
               "rescue", "rescued", "help", "helped", "nurse", "nursed", "mend", "tend")),
    ("protected", ("defend", "defended", "protect", "protected", "shield", "shielded",
                   "guard", "guarded")),
    ("confided", ("confide", "confided", "confess", "confessed", "trust", "trusted",
                  "share", "shared", "tell", "told")),
    ("honored", ("honor", "honored", "keep", "kept", "swear", "swore", "vow", "vowed",
                 "pledge", "pledged")),
)
_VERB_LOOKUP: dict[str, str] = {v: kind for kind, verbs in _VERB_TABLE for v in verbs if " " not in v}
_VERB_PHRASES: tuple[tuple[str, str], ...] = tuple(
    (v, kind) for kind, verbs in _VERB_TABLE for v in verbs if " " in v
)
_NEGATION_TOKENS = frozenset({
    "not", "never", "no", "refuse", "refuses", "refused", "pretend", "pretends",
    "pretended", "decline", "declines", "declined", "wont", "didnt", "cannot", "cant",
})
_NEGATION_WINDOW = 3

# Standing wants for the authored builtin family (Nyx-authored content in v1;
# cartridge-authored wants are a clean follow-up that owns the schema change).
_NPC_WANTS = {
    "sera": "to keep the candlehouse lit through one more winter",
    "aldric": "to come home without shame",
    "maren": "to see one child leave the mine alive",
    "kael": "to be forgiven for what the work made of him",
    "halda": "to hold the stall against the lord's men",
    "ren": "to be remembered as more than a hawker",
    "gran": "to die in the stone house, not the fen",
}


def npc_want(name: str) -> str:
    return _NPC_WANTS.get(name.lower(), "")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def _valence_for(kind: str) -> float:
    if kind in _SOUR_VALENCE:
        return _SOUR_VALENCE[kind]
    return _WARM_BASE.get(kind, 0.0)


def _phrase_negated(lowered: str, phrase: str) -> bool:
    before = lowered[: lowered.find(phrase)].split()[-_NEGATION_WINDOW:]
    return any(w in _NEGATION_TOKENS for w in before)


def classify_interaction(action: str) -> tuple[str, float]:
    """Classify a committed action's verb into an interaction kind.

    Pure keyword matching with a negation guard. Returns (kind, base_valence);
    ('neutral', 0.0) on no match, ambiguity, or a negated/sarcastic verb. Zero
    LLM. Object resolution (which present NPC) is the caller's job (E3).
    """
    toks = _tokens(action)
    if not toks:
        return ("neutral", 0.0)
    lowered = " ".join(toks)
    for phrase, kind in _VERB_PHRASES:
        if phrase in lowered and not _phrase_negated(lowered, phrase):
            return (kind, _valence_for(kind))
    for i, tok in enumerate(toks):
        kind = _VERB_LOOKUP.get(tok)
        if kind is None:
            continue
        if any(w in _NEGATION_TOKENS for w in toks[max(0, i - _NEGATION_WINDOW):i]):
            return ("neutral", 0.0)
        return (kind, _valence_for(kind))
    return ("neutral", 0.0)


def _names_npc(action_lower: str, npc: CanonNPC) -> bool:
    """True if the NPC's name or role is a word-boundary substring (E3)."""
    for token in (npc.name, npc.role):
        token = token.strip().lower()
        if token and re.search(r"\b" + re.escape(token) + r"\b", action_lower):
            return True
    return False


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _note_for(kind: str, action: str, turn: int) -> str:
    excerpt = re.sub(r"\s+", " ", action).strip()[:48]
    return f"you {kind} them: {excerpt} (t{turn})"[:80]


def _compact_events(events: list[NPCEvent]) -> list[NPCEvent]:
    """Keep the earliest souring scar + the most recent EVENT_CAP-1 events."""
    if len(events) <= EVENT_CAP:
        return events
    recent = events[-(EVENT_CAP - 1):]
    souring = [e for e in events if e.kind in _SOURING_KINDS]
    if souring:
        scar = min(souring, key=lambda e: e.turn)
        if scar not in recent:
            return [scar] + recent
    return events[-EVENT_CAP:]


def _record_souring(npc: CanonNPC, kind: str, action: str, turn: int) -> str:
    if kind == "betrayed":
        prior = npc.betrayal_count
        effective = -2.0 - 0.5 * min(prior, 4)                          # compounds, capped at -4
        npc.betrayal_weight = _clamp(npc.betrayal_weight + 1.0 + 0.5 * prior, 0.0, 10.0)
        npc.betrayal_count = min(npc.betrayal_count + 1, 99)            # monotone integer (E6)
    else:
        effective = _SOUR_VALENCE[kind]
    npc.bond = _clamp(npc.bond + effective, -10.0, 10.0)
    npc.events.append(NPCEvent(turn=turn, kind=kind, valence=_SOUR_VALENCE[kind],
                               note=_note_for(kind, action, turn)))
    npc.events = _compact_events(npc.events)
    return f"{npc.name} will not forget being {kind}."


def _record_warming(npc: CanonNPC, kind: str, action: str, turn: int) -> None:
    base = _WARM_BASE[kind]
    throttle = max(0.0, 1.0 - npc.betrayal_weight / 5.0)               # past weight 5, no warmth
    npc.bond = _clamp(npc.bond + base * throttle, -10.0, 10.0)
    npc.events.append(NPCEvent(turn=turn, kind=kind, valence=base,
                               note=_note_for(kind, action, turn)))
    npc.events = _compact_events(npc.events)


def update_npc_relations(state: ThreadState, action: str, outcome) -> list[str]:
    """Fold the committed turn into each present NPC's friction-weighted memory.

    The SOLE writer of bond/events/betrayal. Pure, deterministic, zero LLM.
    Souring/warming applies ONLY to a present NPC named in the committed action
    (E3); un-named present NPCs are presence-only (last_seen bump). Returns at
    most 2 souring notes for Clotho.
    """
    assert getattr(outcome, "action_valid", True), "rejected actions never reach memory"
    canon = state.canon
    if not canon or not canon.current_scene:
        return []

    turn = state.session.turn_count
    oath_broken = bool(getattr(outcome, "oath_broken", None))
    action_lower = action.lower()
    base_kind, _ = classify_interaction(action)
    notes: list[str] = []

    for npc_id in _alive_present_ids(canon, canon.current_scene.present_npc_ids):
        npc = canon.npcs[npc_id]
        npc.last_seen_turn = turn                       # every present NPC, stationary too (E6)

        if not _names_npc(action_lower, npc):
            continue                                    # presence-only — no scene-wide valence (E3)

        kind = base_kind
        # Breaking an oath that names this NPC IS the betrayal (a committed player act).
        if oath_broken and kind in ("neutral", "harmed"):
            kind = "betrayed"
        if kind == "neutral":
            continue

        if kind in _SOURING_KINDS:
            notes.append(_record_souring(npc, kind, action, turn))
        else:
            _record_warming(npc, kind, action, turn)

    return notes[:2]


_BOND_BANDS = (
    (-6.0, "will not forgive you"),
    (-2.0, "wary, souring"),
    (2.0, "guarded"),
    (6.0, "warm but wary"),
)


def _bond_band(bond: float) -> str:
    for ceiling, label in _BOND_BANDS:
        if bond < ceiling:
            return label
    return "would die for you"


def render_npc_interior(npc: CanonNPC) -> str:
    """A compact, deterministic interior gloss for a present NPC (read-only)."""
    parts = [f"{npc.name} ({npc.role})"]
    if npc.want:
        parts.append(f"wants {npc.want}")
    parts.append(f"bond: {_bond_band(npc.bond)}")
    heavy = sorted(npc.events, key=lambda e: (-abs(e.valence), e.turn))[:2]
    mems = "; ".join(e.note for e in heavy if e.note)
    if mems:
        parts.append(f"remembers: {mems}")
    return " — ".join(parts)
