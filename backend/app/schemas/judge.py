"""Sophia's verdict — the semantic judge's value objects.

Frozen, extra='forbid' (the morpheus convention). DELIBERATELY carries no
updated_state, vector_deltas, pressure, doom, death flag, or
corrected_prose-it-authored field — the schema is structurally incapable of
expressing a state write (ADJ-E2). The only string that can re-enter
generation is critique_brief, rendered deterministically by the engine from
the typed violations (never raw model free-text), and it is fed back to
Clotho (lowest authority) where Momus + Sophia re-police it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JudgeViolation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    axis: Literal["beat", "voice", "tragedy"]
    severity: Literal["soft", "hard"]
    detail: str = ""


class JudgeCritique(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["pass", "revise"] = "pass"
    beat_score: float = 1.0
    voice_score: float = 1.0
    tragedy_score: float = 1.0
    violations: list[JudgeViolation] = Field(default_factory=list)
    critique_brief: str = ""
    judged: bool = True
