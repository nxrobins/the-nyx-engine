"""Doom Engine — staged death sentences.

Tragedy lives in the gap between transgression and ruin. A doom is a
death that has already been decided but has not yet arrived: it begins,
it escalates each turn, and at its final stage Atropos severs the thread.

Two species of doom:
  * Inescapable (broken oath, lethal clock) — nothing lifts it. The
    player gets the closing-in, not a reprieve. Chaos (Eris miracle)
    can still cheat the final blow for one turn, as ever.
  * Escapable (wounds, faction heat) — answering the cause before the
    final stage lifts it. The world forgets slowly, but it forgets.

Zero LLM tokens — pure deterministic state machine. The kernel owns
the call sites; Atropos reads the verdict.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.state import DoomState, ThreadState

logger = logging.getLogger("nyx.doom")


# Stage-keyed escalation language, fed to Clotho as directive text.
# Index = how many stages REMAIN before the thread is severed.
_ESCALATION_BY_REMAINING: dict[int, str] = {
    2: (
        "The doom is sealed but distant. Let it manifest as wrongness at "
        "the edges: animals refuse the player, fires burn low around them, "
        "strangers avert their eyes. Do not name death."
    ),
    1: (
        "The doom is close. The world actively closes in: paths are blocked, "
        "allies withdraw, the prophecy's imagery starts appearing in real "
        "objects and weather. The player should feel hunted by the story itself."
    ),
    0: (
        "The doom arrives THIS SCENE. Everything in the scene is an "
        "instrument of it. Do not soften, do not delay, do not offer escape."
    ),
}


def begin_doom(
    state: ThreadState,
    *,
    cause: str,
    description: str,
    max_stage: int = 3,
    escapable: bool = False,
    escape_hint: str = "",
) -> bool:
    """Start a doom sequence at stage 1. Returns True if it took hold.

    An active inescapable doom is never replaced. An active escapable
    doom is replaced only by an inescapable one — fate outranks misfortune.
    """
    current = state.doom
    if current.active:
        if current.escapable and not escapable:
            logger.info(
                f"Doom upgraded: '{current.cause}' (escapable) → '{cause}' (sealed)"
            )
        else:
            return False

    state.doom = DoomState(
        active=True,
        cause=cause,
        description=description,
        stage=1,
        max_stage=max_stage,
        started_turn=state.session.turn_count,
        escapable=escapable,
        escape_hint=escape_hint,
    )
    logger.info(f"DOOM BEGUN: {cause} (stage 1/{max_stage}, escapable={escapable})")
    return True


def _escape_met(state: ThreadState) -> bool:
    """Check whether an escapable doom's lifting condition is satisfied."""
    doom = state.doom
    if doom.cause == "wounds":
        return state.pressures.wounds <= settings.wounds_doom_escape
    if doom.cause == "faction_heat":
        return state.pressures.faction_heat <= settings.faction_doom_escape
    return False


def advance_doom(state: ThreadState) -> str:
    """One turn of doom progression. Called at the top of each turn.

    Escapable dooms are checked for their lifting condition first.
    Returns a short note for logging/trace, or "" when nothing happened.
    """
    doom = state.doom
    if not doom.active:
        return ""

    if doom.escapable and _escape_met(state):
        note = f"The doom of {doom.cause} lifts — the cause was answered."
        logger.info(f"DOOM ESCAPED: {doom.cause} at stage {doom.stage}")
        state.doom = DoomState()
        return note

    doom.stage = min(doom.stage + 1, doom.max_stage)
    logger.info(f"Doom advances: {doom.cause} stage {doom.stage}/{doom.max_stage}")
    return f"The doom of {doom.cause} advances ({doom.stage}/{doom.max_stage})."


def maybe_begin_pressure_dooms(state: ThreadState) -> str:
    """Start escapable dooms from runaway pressures. Returns a note or ""."""
    if state.doom.active:
        return ""

    pressures = state.pressures
    if pressures.wounds >= settings.wounds_doom_threshold:
        begin_doom(
            state,
            cause="wounds",
            description=(
                "The body is failing. Untreated wounds have festered past "
                "the point where willpower substitutes for blood."
            ),
            max_stage=3,
            escapable=True,
            escape_hint="Rest, binding, or a healer — before the body gives out.",
        )
        return "Wounds have turned mortal: a doom begins."

    if pressures.faction_heat >= settings.faction_doom_threshold:
        begin_doom(
            state,
            cause="faction_heat",
            description=(
                "Organized power has decided the player is worth killing. "
                "The hunt is no longer passive."
            ),
            max_stage=3,
            escapable=True,
            escape_hint="Flee the region, buy forgiveness, or break the hunt.",
        )
        return "The hunt begins in earnest: a doom begins."

    return ""


def is_doom_terminal(state: ThreadState) -> bool:
    """True when the doom has reached its final stage — Atropos may cut."""
    doom = state.doom
    return doom.active and doom.stage >= doom.max_stage


def doom_death_reason(state: ThreadState) -> str:
    """Compose the staged death reason for Atropos."""
    doom = state.doom
    base = doom.description or "The doom that was promised arrives."
    by_cause = {
        "broken_oath": (
            "The oath you broke has finished its work. What was sworn and "
            "betrayed claims its price in full."
        ),
        "wounds": "The body, asked once too often, declines. The thread frays from the flesh inward.",
        "faction_heat": "The hunters close the last door. There is no crowd to vanish into this time.",
        "clock": "The reckoning you let mature collects its debt.",
    }
    return f"{by_cause.get(doom.cause, base)}"


def doom_directive(state: ThreadState) -> str:
    """Stage-appropriate dread escalation for Clotho's context."""
    doom = state.doom
    if not doom.active:
        return ""
    remaining = max(doom.max_stage - doom.stage, 0)
    escalation = _ESCALATION_BY_REMAINING.get(
        remaining, _ESCALATION_BY_REMAINING[2]
    )
    lines = [
        f"A DOOM IS ACTIVE ({doom.stage}/{doom.max_stage}): {doom.description}",
        escalation,
    ]
    if doom.escapable and doom.escape_hint and remaining > 0:
        lines.append(
            f"The doom can still be escaped: {doom.escape_hint} "
            "Let that path be visible in the scene, and let it cost something."
        )
    return "\n".join(lines)
