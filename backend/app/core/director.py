"""The Adult Director — procedural beat selection for turn 10+.

Childhood (turns 1-9) runs on authored beats. Adulthood gets no script —
but the lesson of Sprints 8-10 stands: Clotho drifts without a directive
every turn. This module composes one deterministically from live state.

Structure: adult life runs in 3-turn chapters with the same cadence as
childhood epochs (SETUP → COMPLICATION → RESOLUTION), so scene isolation
and time skips keep working. Content: the directive's dramatic driver is
selected by priority from what the engine already knows —

    doom > maturing clock > active oath > loudest pressure
         > hamartia temptation > the world itself

Zero LLM tokens. Pure string assembly from state.
"""

from __future__ import annotations

from app.schemas.state import SceneClock, ThreadState

ADULT_CADENCE: tuple[str, str, str] = ("SETUP", "COMPLICATION", "RESOLUTION")

# Position skeletons follow the Sprint 10 conventions: explicit scene
# breaks, time skips, names, dialogue, immediate consequence.
_POSITION_SKELETONS: dict[str, str] = {
    "SETUP": (
        "NEW SCENE. Time has passed since the last scene — days or weeks. "
        "Establish where the player now is through one specific physical "
        "activity ALREADY IN PROGRESS. Use NAMES from the canon and factual "
        "record. End the scene by introducing the pressure named below as "
        "something concrete: a sound, an arrival, a thing out of place."
    ),
    "COMPLICATION": (
        "NEW SCENE. Time has passed since the last scene. The situation "
        "named below escalates through a PERSON: someone arrives, demands, "
        "reveals, or refuses. Use DIALOGUE — the conversation is the scene. "
        "Reference characters and places by NAME."
    ),
    "RESOLUTION": (
        "NEW SCENE. The situation named below reaches a breaking point in "
        "this scene. The player must act, and the consequence must be "
        "IMMEDIATE and visible: something is gained or lost for good, and "
        "someone present will remember it."
    ),
}

_PRESSURE_DRIVERS: dict[str, str] = {
    "suspicion": (
        "THE DRIVER — SUSPICION ({value:.1f}): someone has been asking "
        "about the player by name. Put the watcher in the scene: half-seen, "
        "or questioning someone the player knows."
    ),
    "scarcity": (
        "THE DRIVER — SCARCITY ({value:.1f}): money, food, or shelter runs "
        "out in this scene. Make the lack physical and immediate, not abstract."
    ),
    "wounds": (
        "THE DRIVER — WOUNDS ({value:.1f}): the body interrupts. Pain "
        "arrives mid-action; something ordinary becomes suddenly hard."
    ),
    "debt": (
        "THE DRIVER — DEBT ({value:.1f}): the creditor or their agent "
        "appears. They are polite and reasonable, which is worse."
    ),
    "faction_heat": (
        "THE DRIVER — FACTION HEAT ({value:.1f}): organized power moves. "
        "A checkpoint, a posted notice, a name read aloud in a public place."
    ),
    "omen": (
        "THE DRIVER — OMEN ({value:.1f}): fate intrudes through real "
        "objects and weather, never narration. The prophecy's imagery "
        "surfaces in the mundane."
    ),
}

_PRESSURE_DRIVER_THRESHOLD = 2.0


def _maturing_clock(state: ThreadState) -> SceneClock | None:
    """Return the active clock nearest to firing, if any is one tick away."""
    canon = state.canon
    if not canon or not canon.current_scene:
        return None
    best: SceneClock | None = None
    for clock_id in canon.current_scene.active_clock_ids:
        clock = canon.clocks.get(clock_id)
        if clock is None:
            continue
        if clock.progress >= clock.max_segments - 1:
            if best is None or clock.progress > best.progress:
                best = clock
    return best


def _loudest_pressure(state: ThreadState) -> tuple[str, float] | None:
    """Return the (name, value) of the strongest driver-eligible pressure."""
    pressures = state.pressures
    candidates = [
        (name, getattr(pressures, name))
        for name in _PRESSURE_DRIVERS
    ]
    name, value = max(candidates, key=lambda item: item[1])
    if value < _PRESSURE_DRIVER_THRESHOLD:
        return None
    return name, value


def _select_driver(state: ThreadState, turn: int) -> str:
    """Pick the dramatic driver for this scene, highest priority first."""
    # 1. An active doom outranks everything. The full escalation text
    #    lives in the stratified context; the driver just aims the scene.
    if state.doom.active:
        doom = state.doom
        return (
            f"THE DRIVER — DOOM ({doom.stage}/{doom.max_stage}): "
            f"{doom.description} This scene is an instrument of it. "
            "Obey the doom directive in your context."
        )

    # 2. A clock one tick from firing demands the stage.
    clock = _maturing_clock(state)
    if clock is not None:
        hint = f" {clock.resolution_hint}" if clock.resolution_hint else ""
        return (
            f"THE DRIVER — THE CLOCK: '{clock.label}' stands at "
            f"{clock.progress}/{clock.max_segments}. Stakes: {clock.stakes} "
            f"This scene must move it toward resolution or collapse.{hint}"
        )

    # 3. An active oath gets tested, not remembered.
    active_oath = next(
        (o for o in state.soul_ledger.active_oaths if o.status == "active"),
        None,
    )
    if active_oath is not None:
        price = ""
        if active_oath.terms and active_oath.terms.price:
            price = f" Its price: {active_oath.terms.price}."
        return (
            f"THE DRIVER — THE OATH: the player swore '{active_oath.text}'."
            f"{price} Stage a situation where keeping it costs something "
            "real, right now."
        )

    # 4. The loudest pressure, if any is loud enough.
    loudest = _loudest_pressure(state)
    if loudest is not None:
        name, value = loudest
        return _PRESSURE_DRIVERS[name].format(value=value)

    # 5. The hamartia tempts. Alternate aim with the world fallback so
    #    consecutive quiet chapters don't repeat one note.
    profile = state.soul_ledger.hamartia_profile
    chapter = (turn - 10) // 3
    if profile is not None and chapter % 2 == 0:
        return (
            f"THE DRIVER — THE FLAW ({profile.name}): {profile.style_directive} "
            "Build the scene as a temptation aimed at this flaw. Make "
            "yielding look easy and attractive; make restraint cost."
        )

    # 6. The world itself. Rotate through canon facts so the settlement
    #    keeps producing texture instead of repeating its loudest fact.
    canon = state.canon
    if canon is not None:
        if canon.current_scene and canon.current_scene.immediate_problem:
            return (
                "THE DRIVER — THE WORLD: "
                f"{canon.current_scene.immediate_problem} "
                "Let this surface concretely in the scene."
            )
        if canon.world_facts:
            fact = canon.world_facts[chapter % len(canon.world_facts)]
            return (
                f"THE DRIVER — THE WORLD: {fact}. "
                "Let this fact surface concretely in the scene."
            )

    return (
        "THE DRIVER — THE WORLD: ordinary life presses in — work, weather, "
        "the cost of staying alive. Ground the scene in one specific task."
    )


def select_adult_beat(state: ThreadState, turn: int) -> tuple[str, str]:
    """Return (beat_position, directive) for an adult turn (10+).

    Deterministic: the same state and turn always produce the same beat.
    """
    position = ADULT_CADENCE[(turn - 10) % len(ADULT_CADENCE)]
    skeleton = _POSITION_SKELETONS[position]
    driver = _select_driver(state, turn)
    return position, f"{skeleton}\n{driver}"
