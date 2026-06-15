"""The World Cartridge contract — the artifact crossing the autonovel↔Nyx boundary.

A cartridge is a versioned, validity-stamped JSON world authored at autonovel's
quality-gated authoring time and consumed deterministically at Nyx runtime. One
file = one world, declaring which first-memory archetypes it serves.

Nyx OWNS this schema (the consumer defines validity); autonovel vendors a mirror
of the emitted `world_cartridge.schema.json`. Neither repo imports the other.

`WorldCartridge.to_world_seed()` produces the exact `WorldSeed` dataclass that
`bootstrap_canon` / `format_world_context` already consume, so nothing downstream
changes — a loaded cartridge is indistinguishable from a hand-authored builtin.

All numeric bounds here are the "Constraints & Fallbacks" matrix made executable:
a breach raises ValidationError, which the registry loader catches per-file and
turns into a skip + WARNING (NC-4). The model never sees an invalid world.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from app.core.world_seeds import WorldSeed

# The supported first-memory archetypes (mirror of kernel._MEMORY_VECTOR_MAP keys).
ARCHETYPES: frozenset[str] = frozenset({"light", "stone", "crowd", "shadow"})

# The one cartridge_version this build understands. Unknown versions fail closed
# at the loader (NC-5); the Literal here makes a mismatch a ValidationError too.
SUPPORTED_VERSION: int = 1

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Stable lowercase slug — MUST stay byte-identical to canon._slug.

    canon.bootstrap_canon keys its npc/location dicts with this exact transform,
    so the in-model uniqueness check (NC-6) is only meaningful if it slugs the
    same way. test_cartridge.py asserts `slugify == canon._slug` over a battery
    of adversarial inputs to guard against drift.
    """
    slug = _SLUG_PATTERN.sub("_", value.lower()).strip("_")
    return slug or "unknown"


class CartridgeNPC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    role: str = Field(min_length=1, max_length=40)
    trait: str = Field(min_length=1, max_length=40)
    trust: float = Field(default=0.0, ge=-10.0, le=10.0)
    fear: float = Field(default=0.0, ge=-10.0, le=10.0)
    obligation: float = Field(default=0.0, ge=-10.0, le=10.0)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("tags")
    @classmethod
    def _tags_bounded(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not 1 <= len(tag) <= 30:
                raise ValueError(f"tag '{tag[:20]}' must be 1..30 chars")
        return tags


class CartridgeClock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    max_segments: int = Field(default=4, ge=1, le=12)
    stakes: str = Field(min_length=1, max_length=400)
    resolution_hint: str = Field(default="", max_length=400)
    lethal: bool = False


class HomeLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_]{2,63}$")
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=60)
    condition: str = Field(min_length=1, max_length=400)


class Faction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_]{2,63}$")
    name: str = Field(min_length=1, max_length=80)
    stance: str = Field(min_length=1, max_length=40)
    notes: str = Field(min_length=1, max_length=400)


class WorldCartridge(BaseModel):
    """A complete, validated, deterministic world ready for Nyx to incarnate."""

    model_config = ConfigDict(extra="forbid")

    # ── Provenance / validity stamp ───────────────────────────────
    cartridge_version: Literal[1]
    world_id: str = Field(min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    generated_by: str = Field(min_length=1, max_length=120)
    source_hash: str = Field(min_length=1, max_length=128)
    archetypes: list[str] = Field(min_length=1, max_length=4)

    # ── World identity (consumer-read → required, NC-9) ───────────
    settlement: str = Field(min_length=1, max_length=80)
    settlement_type: str = Field(min_length=1, max_length=60)
    region: str = Field(min_length=1, max_length=60)
    social_class: str = Field(min_length=1, max_length=120)
    active_situation: str = Field(min_length=1, max_length=600)
    world_facts: list[str] = Field(min_length=3, max_length=20)
    family: list[CartridgeNPC] = Field(min_length=1, max_length=12)
    home_location: HomeLocation
    faction: Faction
    # Authored scene clocks. to_world_seed() carries these into WorldSeed.clocks,
    # and bootstrap_canon instantiates them as live SceneClocks (the single
    # settlement-pressure clock is synthesized only when this list is empty).
    # Lethality is rail-guarded at the Nyx loader, never trusted from the file
    # (see canon._instantiate_authored_clocks): the world supplies stakes + a
    # bool; it never gains authority to sever.
    clocks: list[CartridgeClock] = Field(default_factory=list, max_length=8)
    scene_problem: str = Field(min_length=1, max_length=400)
    scene_objective: str = Field(min_length=1, max_length=400)

    # ── Optional (read by nobody in P1; forward slots) ────────────
    relationship_hints: list[str] = Field(default_factory=list, max_length=12)
    mystery: str = Field(default="", max_length=2000)
    voice_notes: str = Field(default="", max_length=1000)

    # ── Validators ────────────────────────────────────────────────

    @field_validator("archetypes")
    @classmethod
    def _archetypes_known_and_unique(cls, archetypes: list[str]) -> list[str]:
        unknown = [a for a in archetypes if a not in ARCHETYPES]
        if unknown:
            raise ValueError(
                f"unknown archetype(s) {unknown}; allowed: {sorted(ARCHETYPES)}"
            )
        if len(set(archetypes)) != len(archetypes):
            raise ValueError("duplicate archetypes")
        return archetypes

    @field_validator("world_facts")
    @classmethod
    def _facts_bounded(cls, facts: list[str]) -> list[str]:
        for fact in facts:
            if not 1 <= len(fact) <= 280:
                raise ValueError(f"world_fact '{fact[:20]}' must be 1..280 chars")
        return facts

    @field_validator("relationship_hints")
    @classmethod
    def _hints_bounded(cls, hints: list[str]) -> list[str]:
        for hint in hints:
            if not 1 <= len(hint) <= 200:
                raise ValueError(f"relationship_hint '{hint[:20]}' must be 1..200 chars")
        return hints

    @model_validator(mode="after")
    def _slugs_unique(self) -> WorldCartridge:
        """NC-6: no two NPCs / clocks / locations may collide under slugify.

        bootstrap_canon keys its dicts by slugify(name); a collision silently
        drops a canon entity. Reject the whole cartridge instead.
        """
        npc_slugs = [slugify(npc.name) for npc in self.family]
        if len(set(npc_slugs)) != len(npc_slugs):
            dupes = sorted({s for s in npc_slugs if npc_slugs.count(s) > 1})
            raise ValueError(f"NPC name slug collision: {dupes}")

        clock_slugs = [slugify(c.label) for c in self.clocks]
        if len(set(clock_slugs)) != len(clock_slugs):
            dupes = sorted({s for s in clock_slugs if clock_slugs.count(s) > 1})
            raise ValueError(f"clock label slug collision: {dupes}")

        # home_location and faction are single-instance; their ids must differ.
        if self.home_location.id == self.faction.id:
            raise ValueError("home_location.id and faction.id must differ")
        return self

    # ── Adapter to the runtime dataclass ──────────────────────────

    def to_world_seed(self) -> WorldSeed:
        """Produce the exact WorldSeed `bootstrap_canon`/`format_world_context` consume.

        Deferred import keeps the schema layer free of a load-time dependency on
        core/ (world_seeds is a pure leaf, so there is no cycle either way).
        """
        from app.core.world_seeds import SeedClock, WorldNPC, WorldSeed

        return WorldSeed(
            settlement=self.settlement,
            settlement_type=self.settlement_type,
            region=self.region,
            family=[
                WorldNPC(
                    name=npc.name,
                    role=npc.role,
                    trait=npc.trait,
                    trust=npc.trust,
                    fear=npc.fear,
                    obligation=npc.obligation,
                    tags=list(npc.tags),
                )
                for npc in self.family
            ],
            social_class=self.social_class,
            active_situation=self.active_situation,
            world_facts=list(self.world_facts),
            home_location_id=self.home_location.id,
            home_location_name=self.home_location.name,
            home_location_kind=self.home_location.kind,
            home_condition=self.home_location.condition,
            faction_id=self.faction.id,
            faction_name=self.faction.name,
            faction_stance=self.faction.stance,
            faction_notes=self.faction.notes,
            relationship_hints=list(self.relationship_hints),
            default_scene_problem=self.scene_problem,
            default_scene_objective=self.scene_objective,
            clocks=[
                SeedClock(
                    label=c.label,
                    max_segments=c.max_segments,
                    stakes=c.stakes,
                    resolution_hint=c.resolution_hint,
                    lethal=c.lethal,
                )
                for c in self.clocks
            ],
        )
