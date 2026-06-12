"""Assayer P4 contracts — the PlayVerdict.

A finished life, weighed. The Assayer retargets evaluation from "good
prose" to "good *life*": did the world produce decisions, did its clocks
fire, were the story's debts paid, how did the soul move, what killed them.

Verdicts are the telemetry half of the evolution loop: Nyx emits them at
death (deterministically — no LLM judges a life), the Worldsmith consumes
them at authoring time to breed better worlds. The player is the
invariant-checker; the verdict is just the measurement.

Same constitutional posture as every Morpheus artifact: versioned,
stamped, bounded, atomic. A verdict failure costs the verdict, never
the death.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERDICT_VERSION: int = 1


class PlayVerdict(BaseModel):
    """One life, measured. Pure function of the final thread state."""

    model_config = ConfigDict(extra="forbid")

    # ── Provenance / validity stamp ───────────────────────────────
    verdict_version: Literal[1]
    verdict_id: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]{2,119}$")
    world_id: str = Field(min_length=1, max_length=80)
    thread_stamp: str = Field(min_length=3, max_length=120)
    player_name: str = Field(min_length=1, max_length=80)
    book_id: str = Field(default="", max_length=80)

    # ── The shape of the life ─────────────────────────────────────
    hamartia: str = Field(default="", max_length=80)
    died_turn: int = Field(ge=1)
    epochs_reached: int = Field(ge=0, le=64)       # completed 3-turn chapters
    death_cause: str = Field(min_length=1, max_length=600)
    doom_cause: str = Field(default="", max_length=40)  # "" = death without a doom

    # ── The soul at the severing ──────────────────────────────────
    final_vectors: dict[str, float] = Field(default_factory=dict)
    imbalance: float = Field(ge=0.0, le=10.0)

    # ── Did the world do its job? ─────────────────────────────────
    clocks_total: int = Field(ge=0, le=64)
    clocks_fired: int = Field(ge=0, le=64)
    promises_planted: int = Field(ge=0, le=256)
    promises_paid: int = Field(ge=0, le=256)
    promises_abandoned: int = Field(ge=0, le=256)
    oaths_sworn: int = Field(ge=0, le=64)
    oaths_fulfilled: int = Field(ge=0, le=64)
    oaths_broken: int = Field(ge=0, le=64)
    pressures_at_death: dict[str, float] = Field(default_factory=dict)
