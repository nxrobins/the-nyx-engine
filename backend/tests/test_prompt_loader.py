"""Tests for the prompt_loader service — YAML-based system prompt loading.

Covers: load_prompt caching, reload_prompt, reload_all, error handling,
and verifies all 6 agent prompts load correctly.
"""

import pytest

from app.services.prompt_loader import _cache, load_prompt, reload_all, reload_prompt


# ---------------------------------------------------------------------------
# All 6 agents load successfully
# ---------------------------------------------------------------------------

_AGENT_NAMES = ["clotho", "lachesis", "nemesis", "eris", "hypnos", "chronicler"]


class TestLoadAllAgents:
    """Every agent YAML file exists and loads a non-empty prompt."""

    @pytest.mark.parametrize("agent", _AGENT_NAMES)
    def test_loads_prompt(self, agent: str):
        prompt = load_prompt(agent)
        assert isinstance(prompt, str)
        assert len(prompt) > 50  # all prompts are substantial

    @pytest.mark.parametrize("agent", _AGENT_NAMES)
    def test_prompt_starts_with_identity(self, agent: str):
        """Each prompt should start with 'You are ...'."""
        prompt = load_prompt(agent)
        assert prompt.startswith("You are ")


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_cache_populated_after_load(self):
        _cache.clear()
        load_prompt("clotho")
        assert "clotho" in _cache

    def test_cached_value_matches(self):
        first = load_prompt("clotho")
        second = load_prompt("clotho")
        assert first is second  # same object from cache


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------

class TestReload:
    def test_reload_prompt_clears_cache_entry(self):
        load_prompt("hypnos")
        assert "hypnos" in _cache
        result = reload_prompt("hypnos")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_reload_all(self):
        _cache.clear()
        reload_all()
        assert len(_cache) == 6
        for agent in _AGENT_NAMES:
            assert agent in _cache


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_agent_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_prompt("nonexistent")

    def test_missing_agent_not_cached(self):
        _cache.pop("nonexistent", None)
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent")
        assert "nonexistent" not in _cache


# ---------------------------------------------------------------------------
# Content spot-checks
# ---------------------------------------------------------------------------

class TestContentSpotChecks:
    """Verify key phrases survived the YAML migration intact."""

    def test_clotho_has_iceberg_principle(self):
        prompt = load_prompt("clotho")
        assert "ICEBERG PRINCIPLE" in prompt

    def test_clotho_has_kinetic_constraint(self):
        prompt = load_prompt("clotho")
        assert "KINETIC CONSTRAINT" in prompt

    def test_lachesis_has_soul_ledger(self):
        prompt = load_prompt("lachesis")
        assert "THE SOUL LEDGER" in prompt

    def test_lachesis_has_json_schema(self):
        prompt = load_prompt("lachesis")
        assert "valid_action" in prompt

    def test_nemesis_has_prophecy_rules(self):
        prompt = load_prompt("nemesis")
        assert "PROPHECY RULES" in prompt

    def test_eris_has_chaos_incarnate(self):
        prompt = load_prompt("eris")
        assert "CHAOS INCARNATE" in prompt

    def test_hypnos_has_ellipsis_rule(self):
        prompt = load_prompt("hypnos")
        assert "ellipsis" in prompt

    def test_chronicler_has_compression_rule(self):
        prompt = load_prompt("chronicler")
        assert "single mythic sentence" in prompt
