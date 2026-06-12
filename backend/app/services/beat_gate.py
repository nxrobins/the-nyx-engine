"""Beat Gate — the deterministic screen every authored beat must pass.

Momus mocks the Author too: Morpheus's beat sheets face the same kind of
mechanical law Clotho's prose does. Two layers, both pure:

  gate_beat()         — harvest-time: Sprint-10 craft conventions made
                        executable (scene isolation, named grounding,
                        anti-mysticism, sane length), plus precondition
                        names must exist in canon at all.
  preconditions_hold()— consume-time: validate-at-the-moment-of-use.
                        The NPC must be alive NOW, the clock unfired NOW.
                        Staleness costs one beat; the floor plays.

Zero LLM tokens.
"""

from __future__ import annotations

from app.schemas.morpheus import AuthoredBeat
from app.schemas.state import ThreadState

# Law VII vocabulary, enforced on the Author's directives. Deliberately
# duplicated from the autonovel exporter's screen — organs do not share
# code across boundaries, they share law.
MYSTICISM_BANNED: tuple[str, ...] = (
    "fractured realit", "fractured world", "threshold between worlds",
    "between worlds", "realm between", "the void", "ethereal", "otherworld",
    "reality bends", "reality shifts", "fabric of realit", "fabric of the world",
    "chamber of mirrors", "multiplying mirror", "impossible geometr",
    "shimmering veil", "veil between", "shifting reality", "liminal space",
    "shadowed threshold", "dimension", "astral",
)


def _alive_npc_names(state: ThreadState) -> set[str]:
    if not state.canon:
        return set()
    return {npc.name for npc in state.canon.npcs.values() if npc.status == "alive"}


def _known_clock_ids(state: ThreadState) -> set[str]:
    if not state.canon:
        return set()
    return set(state.canon.clocks.keys())


def gate_beat(beat: AuthoredBeat, state: ThreadState) -> list[str]:
    """Harvest-time lint. Returns violations; empty list = the beat may serve."""
    violations: list[str] = []
    directive = beat.directive
    lowered = directive.lower()

    # Scene isolation — the Sprint 10 convention, non-negotiable.
    if not directive.lstrip().startswith("NEW SCENE"):
        violations.append("directive must start with 'NEW SCENE' (scene isolation)")

    # Anti-mysticism: the Author writes the same physical world everyone else does.
    for term in MYSTICISM_BANNED:
        if term in lowered:
            violations.append(f"mysticism: '{term}' is forbidden in a beat directive")

    # Named grounding: the beat must touch the world that exists — at least
    # one living canon NPC referenced by name.
    alive = _alive_npc_names(state)
    if alive and not any(name in directive for name in alive):
        violations.append(
            "directive references no living canon NPC by name "
            f"(known: {sorted(alive)[:6]})"
        )

    # Precondition names must at least exist (liveness is checked at consume).
    for name in beat.preconditions.npcs_alive:
        if state.canon and not any(
            npc.name == name for npc in state.canon.npcs.values()
        ):
            violations.append(f"precondition names unknown NPC '{name}'")
    known_clocks = _known_clock_ids(state)
    for clock_id in beat.preconditions.clocks_unfired:
        if known_clocks and clock_id not in known_clocks:
            violations.append(f"precondition names unknown clock '{clock_id}'")

    return violations


def preconditions_hold(beat: AuthoredBeat, state: ThreadState) -> bool:
    """Consume-time check against LIVE canon. A plan is a suggestion;
    canon is the truth at the moment of use."""
    canon = state.canon
    if canon is None:
        # No canon to check against — only beats with no preconditions hold.
        return not beat.preconditions.npcs_alive and not beat.preconditions.clocks_unfired

    alive = {npc.name for npc in canon.npcs.values() if npc.status == "alive"}
    for name in beat.preconditions.npcs_alive:
        if name not in alive:
            return False

    for clock_id in beat.preconditions.clocks_unfired:
        clock = canon.clocks.get(clock_id)
        if clock is None or clock.progress >= clock.max_segments:
            return False

    return True
