"""Morpheus P2 contracts — the Promise Ledger and the Beat Sheet.

The Re-Outliner authors the NEXT epoch from the LIVED one, behind the
Hypnos dream-curtain. Its outputs cross into the runtime only through
these typed artifacts, under the constitutional law: Morpheus may author
the future and revise the telling — never a lived fact. Mechanically:

  * A Promise must cite a lived turn (event_turn <= the snapshot it was
    authored from). Plants are noticed, not invented.
  * A BeatSheet carries validity stamps (thread_stamp, based_on_turn) and
    per-beat machine-checkable preconditions. The kernel re-validates at
    the moment of use — a plan is a suggestion, canon is the truth.
  * Every bound is executable; a breach is a ValidationError, and the
    deterministic floor (authored childhood beats / the Adult Director)
    plays instead. Morpheus can die mid-sentence and the game never knows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHEET_VERSION: int = 1

# Boring limits.
MAX_ACTIVE_PROMISES = 10
MAX_NEW_PLANTS_PER_SHEET = 2
PAYOFF_WINDOW_MAX = 12   # turns a promise may stay open before it expires


# ---------------------------------------------------------------------------
# The Promise Ledger
# ---------------------------------------------------------------------------

class Promise(BaseModel):
    """A narrative obligation: something lived that the story owes attention.

    Structure is what makes long-range quality an accounting problem:
    a plant is a typed debt with a deadline, not a hope.
    """
    model_config = ConfigDict(extra="forbid")

    promise_id: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]{2,39}$")
    description: str = Field(min_length=10, max_length=300)   # what was planted, concretely
    event_turn: int = Field(ge=1)                             # the lived turn it cites
    significance: str = Field(default="", max_length=300)     # hypothesis: why it matters
    due_turn: int = Field(ge=1)                               # payoff window closes here
    status: Literal["planted", "promoted", "paid", "abandoned"] = "planted"
    paid_turn: int = 0

    @model_validator(mode="after")
    def _window_sane(self) -> Promise:
        if self.due_turn <= self.event_turn:
            raise ValueError("due_turn must be after event_turn")
        if self.due_turn - self.event_turn > PAYOFF_WINDOW_MAX:
            raise ValueError(f"payoff window exceeds {PAYOFF_WINDOW_MAX} turns")
        return self


class LedgerUpdates(BaseModel):
    """The Re-Outliner's proposed ledger changes — applied only through
    promise_engine.apply_ledger_updates, which validates every citation."""
    model_config = ConfigDict(extra="forbid")

    new_plants: list[Promise] = Field(default_factory=list, max_length=MAX_NEW_PLANTS_PER_SHEET)
    promote_ids: list[str] = Field(default_factory=list, max_length=4)


# ---------------------------------------------------------------------------
# The Beat Sheet
# ---------------------------------------------------------------------------

class BeatPrecondition(BaseModel):
    """Machine-checkable facts a beat depends on. Checked against live
    canon at the moment of use (validate-on-consume) — staleness costs
    one beat, never the plan, never the turn."""
    model_config = ConfigDict(extra="forbid")

    npcs_alive: list[str] = Field(default_factory=list, max_length=6)     # canon names
    clocks_unfired: list[str] = Field(default_factory=list, max_length=4) # clock ids


class AuthoredBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Literal["SETUP", "COMPLICATION", "RESOLUTION"]
    directive: str = Field(min_length=50, max_length=1200)
    preconditions: BeatPrecondition = Field(default_factory=BeatPrecondition)
    pays_promise_ids: list[str] = Field(default_factory=list, max_length=3)


class BeatSheet(BaseModel):
    """One authored epoch: up to three beats, stamped against the snapshot
    they were authored from. The Director treats each beat as a suggestion
    that must re-earn its place at consumption time."""
    model_config = ConfigDict(extra="forbid")

    sheet_version: Literal[1]
    thread_stamp: str = Field(min_length=3, max_length=120)   # "player_id:run_number"
    epoch_start_turn: int = Field(ge=2)                       # first turn this sheet serves
    based_on_turn: int = Field(ge=1)                          # snapshot turn (== epoch_start_turn - 1)
    beats: list[AuthoredBeat] = Field(min_length=1, max_length=3)
    ledger_updates: LedgerUpdates = Field(default_factory=LedgerUpdates)

    @model_validator(mode="after")
    def _stamps_coherent(self) -> BeatSheet:
        if self.based_on_turn != self.epoch_start_turn - 1:
            raise ValueError(
                f"based_on_turn ({self.based_on_turn}) must be epoch_start_turn - 1 "
                f"({self.epoch_start_turn - 1}) — a sheet authored from a different "
                "boundary is stale by definition"
            )
        positions = [b.position for b in self.beats]
        if len(set(positions)) != len(positions):
            raise ValueError(f"duplicate beat positions: {positions}")
        return self

    def beat_for(self, position: str) -> AuthoredBeat | None:
        for beat in self.beats:
            if beat.position == position:
                return beat
        return None


# ---------------------------------------------------------------------------
# The Snapshot (kernel → Morpheus, frozen at the boundary)
# ---------------------------------------------------------------------------

class FloorBeat(BaseModel):
    """The procedural directive Morpheus is invited to elevate."""
    model_config = ConfigDict(extra="forbid")

    turn: int
    position: Literal["SETUP", "COMPLICATION", "RESOLUTION"]
    directive: str


class MorpheusSnapshot(BaseModel):
    """Everything the Re-Outliner sees. Built once at the epoch boundary
    from committed state — Morpheus never reads live state (no shared
    mutable memory, no torn reads; the photograph, not the room)."""
    model_config = ConfigDict(extra="forbid")

    thread_stamp: str
    boundary_turn: int                      # the RESOLUTION turn just completed
    epoch_start_turn: int                   # boundary_turn + 1
    prose_window: list[str]                 # the lived epoch's prose
    factual_chronicle: list[str]
    chronicle: list[str]
    last_action: str
    soul_summary: str                       # vectors + hamartia, rendered
    pressure_summary: str
    npc_names_alive: list[str]
    clock_lines: list[str]                  # "id|label|progress/max"
    active_promises: list[Promise]
    floor_beats: list[FloorBeat]            # the 3 procedural directives to elevate

    @field_validator("floor_beats")
    @classmethod
    def _three_floors(cls, floors: list[FloorBeat]) -> list[FloorBeat]:
        if len(floors) != 3:
            raise ValueError("snapshot must carry exactly the next epoch's 3 floor beats")
        return floors
