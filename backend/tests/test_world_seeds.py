"""Tests for world_seeds — Sprint 10: The World.

Verifies:
- Keyword-based seed lookup (4 archetypes + fallback)
- Content quality (non-empty fields, sufficient detail)
- Format output (contains expected sections)
- Origin immutability (repeated calls return identical output)
"""

from app.core.world_seeds import (
    WORLD_SEEDS,
    WorldNPC,
    WorldSeed,
    format_world_context,
    get_world_seed,
)


class TestWorldSeedLookup:
    """Keyword matching maps first memories to world templates."""

    def test_light_keyword_returns_thornwell(self):
        seed = get_world_seed("A light in the distance I could not reach.")
        assert seed.settlement == "Thornwell"

    def test_stone_keyword_returns_ashfall(self):
        seed = get_world_seed("The weight of a heavy stone in my hand.")
        assert seed.settlement == "Ashfall"

    def test_crowd_keyword_returns_oldgate(self):
        seed = get_world_seed("A crowd shouting a name that was not mine.")
        assert seed.settlement == "Oldgate"

    def test_shadow_keyword_returns_fenward(self):
        seed = get_world_seed("A cold shadow that moved when I moved.")
        assert seed.settlement == "the Fenward"

    def test_unknown_keyword_falls_back_to_shadow(self):
        seed = get_world_seed("Something completely unrecognized.")
        assert seed.settlement == "the Fenward"

    def test_empty_string_falls_back_to_shadow(self):
        seed = get_world_seed("")
        assert seed.settlement == "the Fenward"

    def test_case_insensitive_matching(self):
        seed = get_world_seed("A LIGHT in the DISTANCE")
        assert seed.settlement == "Thornwell"

    def test_full_memory_string_matching(self):
        """The keyword can appear anywhere in the full memory string."""
        seed = get_world_seed("I remember the weight of a heavy stone pressing down.")
        assert seed.settlement == "Ashfall"


class TestWorldSeedContent:
    """Every seed has sufficient content for world-building."""

    def test_each_seed_has_nonempty_settlement(self):
        for key, seed in WORLD_SEEDS.items():
            assert seed.settlement, f"Seed '{key}' has empty settlement"

    def test_each_seed_has_at_least_one_family_member(self):
        for key, seed in WORLD_SEEDS.items():
            assert len(seed.family) >= 1, f"Seed '{key}' has no family"

    def test_each_seed_has_nonempty_active_situation(self):
        for key, seed in WORLD_SEEDS.items():
            assert len(seed.active_situation) > 20, (
                f"Seed '{key}' active_situation too short"
            )

    def test_each_seed_has_at_least_3_world_facts(self):
        for key, seed in WORLD_SEEDS.items():
            assert len(seed.world_facts) >= 3, (
                f"Seed '{key}' has only {len(seed.world_facts)} world facts"
            )

    def test_all_npc_names_are_nonempty(self):
        for key, seed in WORLD_SEEDS.items():
            for npc in seed.family:
                assert npc.name, f"Seed '{key}' has NPC with empty name"
                assert npc.role, f"NPC '{npc.name}' in '{key}' has empty role"
                assert npc.trait, f"NPC '{npc.name}' in '{key}' has empty trait"

    def test_no_duplicate_settlement_names(self):
        settlements = [seed.settlement for seed in WORLD_SEEDS.values()]
        assert len(settlements) == len(set(settlements))

    def test_four_world_seeds_exist(self):
        assert len(WORLD_SEEDS) == 4
        assert set(WORLD_SEEDS.keys()) == {"light", "stone", "crowd", "shadow"}


class TestFormatWorldContext:
    """format_world_context produces a complete context block."""

    def test_returns_nonempty_string(self):
        seed = WORLD_SEEDS["light"]
        result = format_world_context(seed, "Achilles", "boy")
        assert len(result) > 50

    def test_contains_settlement_name(self):
        seed = WORLD_SEEDS["stone"]
        result = format_world_context(seed, "Ajax", "boy")
        assert "Ashfall" in result

    def test_contains_family_member_names(self):
        seed = WORLD_SEEDS["stone"]
        result = format_world_context(seed, "Ajax", "boy")
        assert "Maren" in result
        assert "Kael" in result

    def test_contains_active_situation(self):
        seed = WORLD_SEEDS["crowd"]
        result = format_world_context(seed, "Helen", "girl")
        assert "lord's retinue" in result

    def test_contains_world_facts(self):
        seed = WORLD_SEEDS["shadow"]
        result = format_world_context(seed, "Nyx", "girl")
        assert "bog" in result.lower()

    def test_contains_social_class(self):
        seed = WORLD_SEEDS["light"]
        result = format_world_context(seed, "Orpheus", "boy")
        assert "chandler" in result.lower()


class TestOriginImmutability:
    """The world seed data and formatted output must not mutate."""

    def test_format_returns_identical_on_repeated_calls(self):
        seed = WORLD_SEEDS["light"]
        result1 = format_world_context(seed, "Test", "boy")
        result2 = format_world_context(seed, "Test", "boy")
        assert result1 == result2

    def test_seed_data_not_modified_by_format(self):
        seed = WORLD_SEEDS["stone"]
        original_settlement = seed.settlement
        original_facts_count = len(seed.world_facts)
        original_family_count = len(seed.family)

        format_world_context(seed, "Test", "boy")

        assert seed.settlement == original_settlement
        assert len(seed.world_facts) == original_facts_count
        assert len(seed.family) == original_family_count

    def test_get_world_seed_returns_same_object(self):
        """Repeated lookups return the same seed instance."""
        seed1 = get_world_seed("A light in the distance")
        seed2 = get_world_seed("A light in the distance")
        assert seed1 is seed2
