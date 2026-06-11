"""World Registry tests — loading resilience, selection determinism, fallbacks.

Covers the Constraints & Fallbacks rules that live in the loader/selector:
per-file isolation (NC-4), version/encoding/size fail-fast, builtins-always-in-pool
(NC-7), sha256 determinism (NC-8), and the non-derived adversarial fixture (NC-13).
"""

from __future__ import annotations

import json

import pytest

from app.core import world_registry
from app.core.world_registry import WorldRegistry, _match_archetype
from app.core.world_seeds import WORLD_SEEDS


def _adversarial_payload() -> dict:
    """A cartridge NOT derived from any builtin — the real authorability proof.

    Maxed NPC count, unicode throughout, slug-adjacent (but distinct) names,
    every optional omitted. If this loads and converts, the contract is
    sufficient for content the schema author did not hand-craft."""
    return {
        "cartridge_version": 1,
        "world_id": "bleakmoor-7f3a",
        "generated_by": "test-adversarial",
        "source_hash": "deadbeef",
        "archetypes": ["light", "shadow"],
        "settlement": "Bléakmoor",
        "settlement_type": "drowned hamlet",
        "region": "the Núñez Fens",
        "social_class": "eel-trappers — the lowest rung",
        "active_situation": "The tide came early and took the south huts; rent is due regardless.",
        "world_facts": [
            "Salt rots the timber faster than the trappers can cut it",
            "The reeve keeps a ledger no one else may read",
            "Eels run only on the dark of the moon",
            "A bell-tower stands in the water, its bell long gone",
        ],
        "family": [
            {"name": f"Child {i}", "role": "sibling", "trait": "hungry"}
            for i in range(11)
        ] + [{"name": "Gran Ó", "role": "grandmother", "trait": "silent"}],
        "home_location": {
            "id": "bleakmoor_stilthouse",
            "name": "The stilt-house",
            "kind": "raised hovel",
            "condition": "Brackish water laps the floorboards at high tide.",
        },
        "faction": {
            "id": "bleakmoor_reeve",
            "name": "The Reeve's Office",
            "stance": "extractive",
            "notes": "Collects in eels, coin, or labor — never mercy.",
        },
        "scene_problem": "The reeve's man is wading toward the door with the ledger.",
        "scene_objective": "Keep the stilt-house through one more tide.",
    }


@pytest.fixture
def worlds(tmp_path, monkeypatch):
    """Point the registry at an empty tmp dir and return (dir, fresh_registry)."""
    monkeypatch.setattr(world_registry.settings, "worlds_dir", str(tmp_path))
    reg = WorldRegistry()
    return tmp_path, reg


def _write(directory, name: str, payload: dict) -> None:
    (directory / name).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


class TestArchetypeMatch:
    @pytest.mark.parametrize(
        "memory,expected",
        [
            ("A light in the distance", "light"),
            ("The weight of a heavy stone", "stone"),
            ("A crowd shouting a name", "crowd"),
            ("A cold shadow that moved", "shadow"),
            ("nothing recognizable here", None),
        ],
    )
    def test_match(self, memory, expected):
        assert _match_archetype(memory) == expected


class TestEmptyDirFallback:
    def test_empty_dir_uses_builtins(self, worlds):
        directory, reg = worlds
        reg.reload()
        seed = reg.select("a light", player_id="p", run_number=1)
        assert seed == WORLD_SEEDS["light"]

    def test_missing_dir_uses_builtins(self, monkeypatch):
        monkeypatch.setattr(world_registry.settings, "worlds_dir", "/nonexistent/path/xyz")
        reg = WorldRegistry()
        reg.reload()
        assert reg.select("a stone", player_id="p", run_number=1) == WORLD_SEEDS["stone"]


class TestAdversarialFixture:
    """NC-13: a non-derived cartridge must load and convert cleanly."""

    def test_adversarial_loads_and_selects(self, worlds):
        directory, reg = worlds
        _write(directory, "bleakmoor.nyx-world.json", _adversarial_payload())
        reg.reload()
        # 12 NPCs, unicode, two archetypes — pin run so the new world wins is
        # not required; assert it is *reachable* by checking the candidate pool.
        seeds = {
            reg.select("a light", player_id=f"p{n}", run_number=n).settlement
            for n in range(20)
        }
        assert "Bléakmoor" in seeds          # the adversarial world is selectable
        assert "Thornwell" in seeds          # builtin still in the union (NC-7)

    def test_adversarial_npc_count_survives(self, worlds):
        directory, reg = worlds
        _write(directory, "bleakmoor.nyx-world.json", _adversarial_payload())
        reg.reload()
        # Force-select Bleakmoor by scanning runs until it wins, then verify cast.
        for n in range(50):
            seed = reg.select("a shadow", player_id="x", run_number=n)
            if seed.settlement == "Bléakmoor":
                assert len(seed.family) == 12
                assert seed.family[-1].name == "Gran Ó"
                return
        pytest.fail("adversarial world never selected across 50 runs")


class TestDeterminism:
    def test_same_inputs_same_world(self, worlds):
        directory, reg = worlds
        _write(directory, "bleakmoor.nyx-world.json", _adversarial_payload())
        reg.reload()
        a = reg.select("a light", player_id="abc", run_number=7)
        b = reg.select("a light", player_id="abc", run_number=7)
        assert a == b

    def test_different_run_may_differ(self, worlds):
        directory, reg = worlds
        _write(directory, "bleakmoor.nyx-world.json", _adversarial_payload())
        reg.reload()
        settlements = {
            reg.select("a light", player_id="abc", run_number=n).settlement
            for n in range(30)
        }
        # Both the builtin and the adversarial light-world should appear.
        assert len(settlements) >= 2


class TestResilience:
    """NC-4: one bad file never disables the others or the builtins."""

    def test_malformed_json_skipped(self, worlds, caplog):
        directory, reg = worlds
        (directory / "broken.nyx-world.json").write_text("{ not json", encoding="utf-8")
        _write(directory, "bleakmoor.nyx-world.json", _adversarial_payload())
        reg.reload()
        # Good cartridge still loaded; game still selects something valid.
        seed = reg.select("a light", player_id="p", run_number=1)
        assert seed is not None

    def test_schema_violation_skipped(self, worlds):
        directory, reg = worlds
        bad = _adversarial_payload()
        bad["world_facts"] = ["only one"]          # < 3 → ValidationError
        _write(directory, "bad.nyx-world.json", bad)
        reg.reload()
        # Bad world absent; builtin still reachable.
        seed = reg.select("a light", player_id="p", run_number=1)
        assert seed == WORLD_SEEDS["light"]

    def test_oversized_file_skipped(self, worlds):
        directory, reg = worlds
        payload = _adversarial_payload()
        payload["mystery"] = "x" * 1999           # valid field, but we'll pad the file
        # Pad with whitespace to exceed 64 KB without breaking JSON.
        text = json.dumps(payload, ensure_ascii=False) + "\n" + " " * (65 * 1024)
        (directory / "huge.nyx-world.json").write_text(text, encoding="utf-8")
        reg.reload()
        assert "bleakmoor-7f3a" not in reg._loaded_ids

    def test_unsupported_version_skipped(self, worlds):
        directory, reg = worlds
        bad = _adversarial_payload()
        bad["cartridge_version"] = 1  # Literal[1] forbids 2 at parse; simulate a future
        # Write a future-version file by hand so model rejects on version, not Literal.
        future = json.dumps(bad, ensure_ascii=False).replace('"cartridge_version": 1', '"cartridge_version": 99')
        (directory / "future.nyx-world.json").write_text(future, encoding="utf-8")
        reg.reload()
        assert "bleakmoor-7f3a" not in reg._loaded_ids

    def test_duplicate_world_id_skipped(self, worlds):
        directory, reg = worlds
        _write(directory, "a.nyx-world.json", _adversarial_payload())
        _write(directory, "b.nyx-world.json", _adversarial_payload())  # same world_id
        reg.reload()
        # Only one instance kept.
        assert len(reg._loaded_ids) == 1
