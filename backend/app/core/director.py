"""The Adult Director — procedural beat selection for turn 10+.

Childhood (turns 1-9) runs on authored beats. Adulthood gets no script —
but the lesson of Sprints 8-10 stands: Clotho drifts without a directive
every turn. This module composes one deterministically from live state.

Structure: adult life runs in 3-turn chapters with the same cadence as
childhood epochs (SETUP → COMPLICATION → RESOLUTION), so scene isolation
and time skips keep working. Content: the directive's dramatic driver is
selected by priority from what the engine already knows —

    doom > maturing clock > active oath > loudest pressure
         > charged relationship > hamartia temptation > the world itself

Zero LLM tokens. Pure string assembly from state.
"""

from __future__ import annotations

from app.schemas.state import CanonNPC, SceneClock, SessionData, ThreadState

ADULT_CADENCE: tuple[str, str, str] = ("SETUP", "COMPLICATION", "RESOLUTION")

# ---------------------------------------------------------------------------
# THE PULSE — the two-speed beat scheduler (Phase 1, sub-slice 1)
#
# Every turn is a VIGNETTE (cheap, buttons, typed consequence packets, no
# council) or a CRUCIBLE (the full Fates deliberation + console). A chapter is
# 0..N vignettes capped by exactly one crucible; a dream marks every chapter
# boundary. Deterministic, model-free (this module is pinned in
# MODEL_FREE_MODULES). Inert until the kernel wires it (sub-slice 3).
# ---------------------------------------------------------------------------

VIGNETTE = "vignette"
CRUCIBLE = "crucible"

# P1-C1: Nigel's ruling — chapter length scales with age, hard maximum. A birth
# chapter is its single (crucible-grade) beat; the ceiling grows with the
# character's world. The budget is a CEILING, not a promise: drama fires the
# crucible early (see next_beat_kind).
CHAPTER_BUDGET_MAX = 5


def chapter_budget(age: int) -> int:
    """Vignettes allowed before this chapter's crucible, by age (P1-C1)."""
    if age <= 3:
        return 0
    if age <= 7:
        return 1
    if age <= 12:
        return 2
    if age <= 17:
        return 3
    if age <= 29:
        return 4
    return CHAPTER_BUDGET_MAX


def next_beat_kind(state: ThreadState) -> str:
    """Decide this turn's beat kind. Pure: same state, same answer.

    Crucible when:
      - a doom is active — a doomed life is all crisis, and the lethal grain
        lives at crucibles (P1-C4), so doom pacing keeps today's per-beat feel;
      - a clock is one tick from firing — the stage is demanded;
      - the chapter's age-scaled vignette budget is spent (P1-C1).
    Otherwise: a vignette. Oath tests and arrivals stay CRUCIBLE DRIVERS
    (what the crucible stages), not schedule triggers — an active oath lasting
    twenty turns must not collapse twenty chapters into all-crucibles.
    """
    if state.doom.active:
        return CRUCIBLE
    if _maturing_clock(state) is not None:
        return CRUCIBLE
    if state.session.beats_spent >= chapter_budget(state.session.player_age):
        return CRUCIBLE
    return VIGNETTE


def record_beat(session: SessionData, kind: str) -> bool:
    """Bookkeeping after a beat commits. Returns True iff the chapter closed.

    A crucible always closes the chapter (increments chapter_index, resets the
    spent count) — the True return is the dream boundary (P1-C10). A vignette
    spends one beat of the budget.
    """
    session.beat_kind = kind
    if kind == CRUCIBLE:
        session.chapter_index += 1
        session.beats_spent = 0
        return True
    session.beats_spent += 1
    return False

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


# A present bond this charged — by warmth, estrangement, or a pattern of betrayal —
# is dramatic enough to drive a quiet chapter on its own.
_RELATIONSHIP_DRIVER_CHARGE = 3.0


def _charged_relationship(state: ThreadState) -> CanonNPC | None:
    """The most charged present, living witness — if any bond is dramatic enough.

    Charge = max(|bond|, betrayal_count * 2): a deep tie, a deep estrangement, or a
    pattern of betrayal all qualify. Deterministic, reads only the merged Sprint-D
    relationship state, no model. Returns None when no present bond is charged
    enough, so the existing hamartia/world fallback still drives the quiet chapter.
    """
    canon = state.canon
    if not canon or not canon.current_scene:
        return None
    best: CanonNPC | None = None
    best_charge = 0.0
    for npc_id in canon.current_scene.present_npc_ids:
        npc = canon.npcs.get(npc_id)
        if npc is None or npc.status != "alive":
            continue
        charge = max(abs(npc.bond), npc.betrayal_count * 2.0)
        if charge >= _RELATIONSHIP_DRIVER_CHARGE and charge > best_charge:
            best = npc
            best_charge = charge
    return best


def _relationship_driver(npc: CanonNPC) -> str:
    """Aim a quiet chapter at a charged bond — a rift to widen or a tie to test."""
    if npc.bond <= -2.0 or npc.betrayal_count >= 1:
        return (
            f"THE DRIVER — THE WITNESS: {npc.name} ({npc.role}) and the player have "
            f"reached a breaking point. Stage a scene that forces the rift between them "
            f"into the open — a confrontation, a demand, a choice that deepens the wound "
            f"or begins to mend it. The bond was real; so is the damage."
        )
    want = f" They want {npc.want}." if npc.want else ""
    return (
        f"THE DRIVER — THE WITNESS: {npc.name} ({npc.role}) matters to the player.{want} "
        f"Stage a scene that puts this bond under real strain — a need, a cost, or a "
        f"conflict between what they want and what the player is willing to give."
    )


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

    # 5. A charged bond among the present cast drives the quiet chapter — the
    #    people, not just the flaw or the world. Earned: only a genuinely charged
    #    relationship (a deep tie, estrangement, or brewing betrayal) qualifies;
    #    otherwise this is silent and the chain falls through unchanged.
    witness = _charged_relationship(state)
    if witness is not None:
        return _relationship_driver(witness)

    # 6. The hamartia tempts. Alternate aim with the world fallback so
    #    consecutive quiet chapters don't repeat one note.
    profile = state.soul_ledger.hamartia_profile
    chapter = (turn - 10) // 3
    if profile is not None and chapter % 2 == 0:
        return (
            f"THE DRIVER — THE FLAW ({profile.name}): {profile.style_directive} "
            "Build the scene as a temptation aimed at this flaw. Make "
            "yielding look easy and attractive; make restraint cost."
        )

    # 7. The world itself. Rotate through canon facts so the settlement
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
