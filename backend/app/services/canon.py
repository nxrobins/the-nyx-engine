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

    present = []
    for npc_id in _alive_present_ids(canon, scene.present_npc_ids):
        npc = canon.npcs[npc_id]
        present.append(f"{npc.name} ({npc.role})")
    if present:
        lines.append("PRESENT: " + ", ".join(present))

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
