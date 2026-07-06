"""Vignette contract v0 — THE PULSE's authored cheap beat (Phase 1, sub-slice 2).

A vignette is AUTHORED CONTENT (Nigel's ruling: the engine selects and binds,
never composes from state): a small grounded situation, an optional cast of
canon roles, and 3-5 button choices each carrying a typed ConsequencePacket the
deterministic layer applies with no council.

The hardened constraints live HERE as validators, so ill-formed content cannot
exist at runtime (lint = the schema):
  P1-C2 — packet caps: |vector Δ| ≤ 1.5, |pressure Δ| ≤ 1.0, |bond Δ| ≤ 1.5.
  P1-C3 — movement floor: ≥1 delta with |Δ| ≥ 0.1 OR an evolution string ≥ 10
          chars. No motion theater.
  Choice sets must span ≥ 3 distinct dominant vectors (who-you-are choices).

Phase 3 (THE FACTORY) grows this into cartridge v2 pools; this v0 is the schema
the hand-authored builtin pools prove.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

VECTOR_DELTA_CAP = 1.5
PRESSURE_DELTA_CAP = 1.0
BOND_DELTA_CAP = 1.5
MOVEMENT_FLOOR = 0.1
EVOLUTION_MIN_CHARS = 10
MIN_CHOICES = 3
MAX_CHOICES = 5
MIN_VECTOR_SPAN = 3

_VECTORS = ("metis", "bia", "kleos", "aidos")
_PRESSURES = (
    "suspicion", "scarcity", "wounds", "debt", "faction_heat", "omen", "exploit_score",
)
_SLOT_RE = re.compile(r"\{([a-z_]+)\}")


class ConsequencePacket(BaseModel):
    """The typed, capped consequence a vignette choice applies — no council."""

    model_config = ConfigDict(extra="forbid")

    vector_deltas: dict[str, float] = Field(default_factory=dict)
    pressure_deltas: dict[str, float] = Field(default_factory=dict)
    # Bond movement toward the vignette's bound cast (first slot), if any.
    bond_delta: float = 0.0
    # How the scene problem evolves after this choice (kills neutral-turn stasis).
    scene_evolution: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _caps_and_floor(self) -> "ConsequencePacket":
        for key, value in self.vector_deltas.items():
            if key not in _VECTORS:
                raise ValueError(f"unknown vector {key!r}")
            if abs(value) > VECTOR_DELTA_CAP:
                raise ValueError(f"vector delta {key}={value} exceeds ±{VECTOR_DELTA_CAP} (P1-C2)")
        for key, value in self.pressure_deltas.items():
            if key not in _PRESSURES:
                raise ValueError(f"unknown pressure {key!r}")
            if abs(value) > PRESSURE_DELTA_CAP:
                raise ValueError(f"pressure delta {key}={value} exceeds ±{PRESSURE_DELTA_CAP} (P1-C2)")
        if abs(self.bond_delta) > BOND_DELTA_CAP:
            raise ValueError(f"bond delta {self.bond_delta} exceeds ±{BOND_DELTA_CAP} (P1-C2)")
        moves = any(
            abs(v) >= MOVEMENT_FLOOR
            for v in (*self.vector_deltas.values(), *self.pressure_deltas.values(), self.bond_delta)
        )
        if not moves and len(self.scene_evolution.strip()) < EVOLUTION_MIN_CHARS:
            raise ValueError(
                "packet moves nothing: needs a delta ≥ "
                f"{MOVEMENT_FLOOR} or scene_evolution ≥ {EVOLUTION_MIN_CHARS} chars (P1-C3)"
            )
        return self

    def dominant_vector(self) -> str:
        """The vector this choice tempts most (for the span rule)."""
        if not self.vector_deltas:
            return ""
        return max(self.vector_deltas, key=lambda k: abs(self.vector_deltas[k]))


class VignetteChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=3, max_length=120)   # the button text — a concrete physical action
    packet: ConsequencePacket


class Vignette(BaseModel):
    """One authored cheap beat, bound to live state at selection time."""

    model_config = ConfigDict(extra="forbid")

    vignette_id: str = Field(min_length=3, max_length=60, pattern=r"^[a-z0-9][a-z0-9_-]{2,59}$")
    # The situation brief the prose surface renders — grounded, concrete,
    # 1-4 sentences. May contain {role} slots bound from canon at selection.
    situation: str = Field(min_length=30, max_length=600)
    # Canon roles that must be ALIVE for this vignette to be eligible; their
    # names bind into the situation's {role} slots.
    cast_slots: list[str] = Field(default_factory=list, max_length=3)
    min_age: int = Field(default=18, ge=0, le=200)
    max_age: int = Field(default=200, ge=0, le=200)
    choices: list[VignetteChoice] = Field(min_length=MIN_CHOICES, max_length=MAX_CHOICES)

    @model_validator(mode="after")
    def _well_formed(self) -> "Vignette":
        if self.max_age < self.min_age:
            raise ValueError("max_age < min_age")
        # Choice sets are who-you-are decisions: ≥3 distinct dominant vectors.
        dominants = {c.packet.dominant_vector() for c in self.choices} - {""}
        if len(dominants) < MIN_VECTOR_SPAN:
            raise ValueError(
                f"choice set spans {len(dominants)} vectors; needs ≥ {MIN_VECTOR_SPAN}"
            )
        # The bow ruling: every choice MUST carry its authored seal — the
        # engine appends scene_evolution as the scene's closing line, so a
        # vignette without one can never audibly shut. No bow, no ship.
        for c in self.choices:
            if len(c.packet.scene_evolution.strip()) < EVOLUTION_MIN_CHARS:
                raise ValueError(
                    f"choice {c.label!r} has no seal: scene_evolution is required "
                    f"(≥ {EVOLUTION_MIN_CHARS} chars) — a vignette must wrap with "
                    f"a bow on top"
                )
        # Every {slot} in the situation must be a declared cast slot.
        unbound = set(_SLOT_RE.findall(self.situation)) - set(self.cast_slots)
        if unbound:
            raise ValueError(f"situation references undeclared slots: {sorted(unbound)}")
        return self


class VignettePool(BaseModel):
    """A world's deck of authored vignettes."""

    model_config = ConfigDict(extra="forbid")

    world_id: str = Field(min_length=3, max_length=80)
    vignettes: list[Vignette] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> "VignettePool":
        ids = [v.vignette_id for v in self.vignettes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate vignette_ids in pool")
        return self


class BoundVignette(BaseModel):
    """A vignette after selection: slots bound to living canon names."""

    vignette_id: str
    situation: str                       # slots replaced with real names
    choices: list[VignetteChoice]
    cast_names: dict[str, str] = Field(default_factory=dict)  # slot -> canon name
