"""Outcome data types for the calibration harness.

Shared by runner (produces them), metrics (aggregates them), and
red_team (scores them). Kept in their own module so runner and metrics
never import each other (no cycle).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The closed enum every terminal life maps to — reconstructed from the
# trace, NEVER from free-text death_reason (CAL-E6).
DEATH_BUCKETS: tuple[str, ...] = (
    "broken_oath",
    "wounds",
    "faction_heat",
    "clock",
    "dead_soul",
    "self_destruct_keyword",
    "narrative_dead_end",
    "__capped__",
)


@dataclass(frozen=True)
class DoomSnapshot:
    """The doom state as recorded after a turn committed."""

    active: bool
    cause: str
    stage: int
    max_stage: int
    started_turn: int
    escapable: bool


@dataclass(frozen=True)
class TurnTrace:
    """One player-action turn's deterministic, measured outcome."""

    turn_number: int
    action: str
    nemesis_struck: bool
    nemesis_type: str           # "" | prophecy_update | punishment | lethal_punishment
    eris_struck: bool
    oath_broken: bool
    doom: DoomSnapshot
    vectors: dict[str, float]
    pressures: dict[str, float]
    last_outcome: str
    terminal: bool
    rag_context_len: int        # MUST be 0 (CAL-E1)


@dataclass
class LifeOutcome:
    """The full record of one scripted life."""

    label: str
    world_id: str
    terminal: bool
    capped: bool
    death_reason: str
    died_turn: int
    final_vectors: dict[str, float]
    turns: list[TurnTrace] = field(default_factory=list)
    verdict: object | None = None        # app.schemas.assay.PlayVerdict
    is_exploit_turn: tuple[bool, ...] = ()
    legitimate: bool = False
