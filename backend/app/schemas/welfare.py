"""The Vigil — Player Safety value objects (frozen, extra='forbid').

A CrisisSignal NEVER carries the matched substring or the action text — only a
boolean and a coarse class — so a player's disclosure cannot ride this object
into a log, a response, or telemetry (SAFE-C1 / AG-C1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CrisisSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    flagged: bool = False
    # Coarse class only — never the matched text. Not persisted (AG-C1).
    pattern_class: Literal["", "ideation", "self_destruct"] = ""


class ContentPrefs(BaseModel):
    """Self-asserted consent state. NOT a verified age wall (AG-C4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    age_affirmed: bool = False
    consent_version: str = ""
