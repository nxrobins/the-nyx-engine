"""WorldCartridge contract tests — schema bounds, slug parity, consumer union.

The cartridge schema is the autonovel↔Nyx boundary; these tests pin the
Constraints & Fallbacks matrix as executable law and guard the two cross-module
invariants the design depends on (slugify ≡ canon._slug, required = consumer union).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.cartridge import (
    ARCHETYPES,
    CartridgeNPC,
    WorldCartridge,
    slugify,
)
from app.services.canon import _slug

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "worlds" / "world_cartridge.schema.json"


def _valid_payload(**overrides) -> dict:
    """A minimal schema-valid cartridge; optionals omitted on purpose."""
    payload = {
        "cartridge_version": 1,
        "world_id": "test-world",
        "generated_by": "test",
        "source_hash": "abc123",
        "archetypes": ["light"],
        "settlement": "Testholm",
        "settlement_type": "village",
        "region": "the Testlands",
        "social_class": "potters",
        "active_situation": "The kiln has gone cold and the winter rent is due.",
        "world_facts": ["A river runs east", "The lord is absent", "Clay is the only wealth"],
        "family": [{"name": "Mara", "role": "mother", "trait": "weary"}],
        "home_location": {
            "id": "test_kiln",
            "name": "The cold kiln",
            "kind": "workshop",
            "condition": "Ash and unfired pots.",
        },
        "faction": {
            "id": "test_guild",
            "name": "Potters' Guild",
            "stance": "wary",
            "notes": "They control the clay pits.",
        },
        "scene_problem": "The rent collector is at the door.",
        "scene_objective": "Keep the family's pitch through winter.",
    }
    payload.update(overrides)
    return payload


class TestSlugParity:
    """NC-6 is only meaningful if cartridge slugify keys exactly like canon."""

    @pytest.mark.parametrize(
        "value",
        ["Old Tom", "Young-Tom", "Séra", "a b c", "!!!", "Café Núñez", "  pad  ", "X"],
    )
    def test_slugify_matches_canon(self, value):
        assert slugify(value) == _slug(value)


class TestValidCartridge:
    def test_minimal_valid(self):
        cart = WorldCartridge.model_validate(_valid_payload())
        assert cart.world_id == "test-world"
        assert cart.clocks == []
        assert cart.mystery == ""

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(secret_field="x"))


class TestPayloadBounds:
    def test_unknown_archetype_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(archetypes=["dreaming"]))

    def test_duplicate_archetypes_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(archetypes=["light", "light"]))

    def test_too_few_world_facts_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(world_facts=["one", "two"]))

    def test_too_many_npcs_rejected(self):
        npcs = [{"name": f"N{i}", "role": "peer", "trait": "x"} for i in range(13)]
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(family=npcs))

    def test_bad_world_id_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(world_id="Has Spaces!"))

    def test_wrong_version_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(cartridge_version=2))

    def test_overlong_active_situation_rejected(self):
        with pytest.raises(ValidationError):
            WorldCartridge.model_validate(_valid_payload(active_situation="x" * 601))


class TestSlugUniqueness:
    def test_npc_slug_collision_rejected(self):
        # "Old Tom" and "Old-Tom" both slug to "old_tom"
        npcs = [
            {"name": "Old Tom", "role": "father", "trait": "hard"},
            {"name": "Old-Tom", "role": "uncle", "trait": "soft"},
        ]
        with pytest.raises(ValidationError, match="slug collision"):
            WorldCartridge.model_validate(_valid_payload(family=npcs))

    def test_home_faction_id_collision_rejected(self):
        payload = _valid_payload()
        payload["faction"]["id"] = payload["home_location"]["id"]
        with pytest.raises(ValidationError, match="must differ"):
            WorldCartridge.model_validate(payload)


class TestConsumerUnion:
    """NC-9: every field bootstrap_canon / format_world_context reads must be
    populated by to_world_seed from a REQUIRED cartridge field. We prove this
    operationally: a cartridge with all optionals omitted still yields a seed
    whose every consumer-read field is non-empty."""

    def test_minimal_cartridge_fills_every_consumer_field(self):
        seed = WorldCartridge.model_validate(_valid_payload()).to_world_seed()
        # format_world_context reads:
        assert seed.settlement and seed.settlement_type and seed.region
        assert seed.social_class and seed.active_situation and seed.world_facts
        assert all(n.name and n.role and n.trait for n in seed.family)
        # bootstrap_canon reads:
        assert seed.home_location_id and seed.home_location_name
        assert seed.home_location_kind and seed.home_condition
        assert seed.faction_id and seed.faction_name and seed.faction_stance and seed.faction_notes
        assert seed.default_scene_problem and seed.default_scene_objective

    def test_only_relationship_hints_may_be_empty(self):
        # The one consumer-read-by-nobody field is allowed empty.
        seed = WorldCartridge.model_validate(_valid_payload()).to_world_seed()
        assert seed.relationship_hints == []


class TestEmittedSchema:
    """The committed schema artifact (vendored by autonovel) must track the model."""

    def test_committed_schema_matches_model(self):
        assert _SCHEMA_PATH.exists(), "world_cartridge.schema.json not committed"
        committed = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        assert committed == WorldCartridge.model_json_schema(), (
            "Committed schema is stale — regenerate world_cartridge.schema.json"
        )

    def test_archetypes_constant_stable(self):
        # The mirror and the kernel memory-map depend on this set.
        assert ARCHETYPES == frozenset({"light", "stone", "crowd", "shadow"})


_WORLDS_DIR = Path(__file__).resolve().parent.parent / "worlds"


class TestBuiltinEquivalence:
    """THE KEYSTONE (A5/NC-13 first half): each shipped cartridge, loaded and
    converted, must be byte-for-byte the builtin it was derived from. This
    proves the schema is sufficient by construction — round-tripping a builtin
    through JSON and back loses nothing the runtime consumes."""

    @pytest.mark.parametrize(
        "filename,archetype",
        [
            ("thornwell.nyx-world.json", "light"),
            ("ashfall.nyx-world.json", "stone"),
            ("oldgate.nyx-world.json", "crowd"),
            ("fenward.nyx-world.json", "shadow"),
        ],
    )
    def test_cartridge_round_trips_to_builtin(self, filename, archetype):
        from app.core.world_seeds import WORLD_SEEDS

        raw = (_WORLDS_DIR / filename).read_text(encoding="utf-8")
        cart = WorldCartridge.model_validate_json(raw)
        assert archetype in cart.archetypes
        assert cart.to_world_seed() == WORLD_SEEDS[archetype]

    def test_all_shipped_cartridges_are_valid(self):
        files = sorted(_WORLDS_DIR.glob("*.nyx-world.json"))
        ids = set()
        for f in files:
            cart = WorldCartridge.model_validate_json(f.read_text(encoding="utf-8"))
            ids.add(cart.world_id)
        # The 4 builtin-equivalents must always ship; minted/bred worlds may add
        # more (World Breadth). The invariant is "every shipped file is valid AND
        # the builtins are all present", not "exactly four".
        assert {"thornwell", "ashfall", "oldgate", "fenward"} <= ids


class TestHermeticityFirewall:
    """NC-14 (Nyx side): the contract is the JSON file. No Nyx test may reach
    across into the autonovel exporter — that would drag a real LLM / network
    dependency into the hermetic suite."""

    def test_no_test_imports_autonovel(self):
        tests_dir = Path(__file__).resolve().parent
        forbidden = ("import autonovel", "from autonovel", "gen_nyx_cartridge")
        offenders = []
        for py in tests_dir.glob("test_*.py"):
            text = py.read_text(encoding="utf-8")
            for needle in forbidden:
                # Skip this assertion's own literals.
                for line in text.splitlines():
                    if needle in line and "forbidden" not in line and "needle" not in line:
                        offenders.append(f"{py.name}: {line.strip()}")
        assert not offenders, f"autonovel reached from Nyx tests: {offenders}"
