"""Tests for Momus — the NER hallucination checker / prose validator.

Covers: environment consistency checks, oath reference validation,
death language detection, multi-hallucination aggregation, and
the base evaluate() passthrough.
"""

from __future__ import annotations

import pytest

from app.agents.momus import Momus
from app.schemas.state import (
    MomusValidation,
    Oath,
    SessionData,
    SoulLedger,
    SoulVectors,
    ThreadState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def momus() -> Momus:
    return Momus()


@pytest.fixture
def desert_state() -> ThreadState:
    """Player is in a desert environment with balanced soul."""
    return ThreadState(
        session=SessionData(
            current_environment="A scorching desert stretching to the horizon.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
        ),
    )


@pytest.fixture
def ocean_state() -> ThreadState:
    """Player is in an ocean environment."""
    return ThreadState(
        session=SessionData(
            current_environment="A dark ocean churning beneath a starless sky.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
        ),
    )


@pytest.fixture
def oath_state() -> ThreadState:
    """Player has an active oath."""
    return ThreadState(
        session=SessionData(
            current_environment="A stone courtyard.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
            active_oaths=[
                Oath(oath_id="oath_1", text="I swear to protect the village.", turn_sworn=3),
            ],
        ),
    )


@pytest.fixture
def no_oath_state() -> ThreadState:
    """Player has NO active oaths."""
    return ThreadState(
        session=SessionData(
            current_environment="A quiet meadow.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
            active_oaths=[],
        ),
    )


@pytest.fixture
def collapsed_soul_state() -> ThreadState:
    """All vectors at or below 1.0 — death is plausible."""
    return ThreadState(
        session=SessionData(
            current_environment="A dim cave.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=0.5, bia=1.0, kleos=0.0, aidos=0.8),
        ),
    )


@pytest.fixture
def healthy_soul_state() -> ThreadState:
    """Healthy soul — death language would be a hallucination."""
    return ThreadState(
        session=SessionData(
            current_environment="An open field.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=6.0, bia=7.0, kleos=5.0, aidos=5.0),
        ),
    )


# ---------------------------------------------------------------------------
# Base evaluate() — always passes
# ---------------------------------------------------------------------------

class TestBaseEvaluate:
    """Momus.evaluate() always returns valid (it's a no-op placeholder)."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_valid(self, momus, fresh_state):
        result = await momus.evaluate(fresh_state, "some action")
        assert isinstance(result, MomusValidation)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_evaluate_returns_no_hallucinations(self, momus, fresh_state):
        result = await momus.evaluate(fresh_state, "attack the wall")
        assert result.hallucinations == []


# ---------------------------------------------------------------------------
# Environment Consistency Checks
# ---------------------------------------------------------------------------

class TestEnvironmentConsistency:
    """Momus detects terrain contradictions in prose."""

    @pytest.mark.asyncio
    async def test_desert_mentioning_ocean_flagged(self, momus, desert_state):
        prose = "You wade into the ocean, salt water stinging your wounds."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is False
        assert len(result.hallucinations) >= 1
        assert any("ocean" in h.lower() or "desert" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_ocean_mentioning_desert_flagged(self, momus, ocean_state):
        prose = "The desert sand stretches endlessly before you."
        result = await momus.validate_prose(prose, ocean_state)
        assert result.valid is False
        assert len(result.hallucinations) >= 1

    @pytest.mark.asyncio
    async def test_matching_environment_passes(self, momus, desert_state):
        prose = "The sand burns beneath your feet as you march onward."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is True
        assert result.hallucinations == []

    @pytest.mark.asyncio
    async def test_ocean_prose_in_ocean_env_passes(self, momus, ocean_state):
        prose = "The waves crash against the hull as the ship lurches starboard."
        result = await momus.validate_prose(prose, ocean_state)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_neutral_prose_passes_any_env(self, momus, desert_state):
        """Prose without terrain keywords should always pass."""
        prose = "The child reached for the door handle and hesitated."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Oath Reference Checks
# ---------------------------------------------------------------------------

class TestOathReferences:
    """Momus catches oath references when no oaths are active."""

    @pytest.mark.asyncio
    async def test_oath_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "The weight of your oath presses down on your shoulders."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False
        assert any("oath" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_sworn_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "You remember what you have sworn, and it steadies your hand."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_vow_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "The vow burns in your chest like a second heartbeat."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_promise_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "You broke your promise. The silence that follows is deafening."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_oath_mention_with_active_oath_passes(self, momus, oath_state):
        """When oaths ARE active, referencing them is correct."""
        prose = "The weight of your oath presses down on your shoulders."
        result = await momus.validate_prose(prose, oath_state)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_no_oath_words_always_passes(self, momus, no_oath_state):
        """Prose without oath keywords passes regardless of oath state."""
        prose = "The child walked through the quiet meadow, watching butterflies."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Death Language Checks
# ---------------------------------------------------------------------------

class TestDeathLanguage:
    """Momus detects inappropriate death declarations."""

    @pytest.mark.asyncio
    async def test_death_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "Your strength fails. You die in the dirt, alone and forgotten."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False
        assert any("death" in h.lower() or "die" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_perish_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "The darkness takes you. You perish in the cold."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_life_ends_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "The blade strikes true. Your life ends here."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_death_with_collapsed_soul_passes(self, momus, collapsed_soul_state):
        """When soul vectors are collapsed (all <= 1.0), death is legitimate."""
        prose = "The last ember of your soul gutters. You die."
        result = await momus.validate_prose(prose, collapsed_soul_state)
        # All vectors <= 1.0, so the death check says "any(v > 3.0)" is False
        # Therefore no hallucination about death
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_near_death_words_without_exact_pattern(self, momus, healthy_soul_state):
        """Words like 'deadly' or 'death' alone (not 'you die') should not trigger."""
        prose = "A deadly silence fills the corridor. Death watches from the shadows."
        result = await momus.validate_prose(prose, healthy_soul_state)
        # The regex looks for exact phrases like "you die", not just the word "death"
        assert result.valid is True


# ---------------------------------------------------------------------------
# Multi-Hallucination Aggregation
# ---------------------------------------------------------------------------

class TestMultiHallucination:
    """Momus can detect multiple hallucination types in one prose."""

    @pytest.mark.asyncio
    async def test_environment_and_oath_violations(self, momus):
        """Prose with both terrain contradiction AND oath reference (no oaths)."""
        state = ThreadState(
            session=SessionData(
                current_environment="A vast desert, dry and merciless.",
            ),
            soul_ledger=SoulLedger(
                vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
                active_oaths=[],
            ),
        )
        prose = "You dive into the ocean, remembering the oath you swore."
        result = await momus.validate_prose(prose, state)
        assert result.valid is False
        assert len(result.hallucinations) >= 2


# ---------------------------------------------------------------------------
# Corrected Prose Pass-Through
# ---------------------------------------------------------------------------

class TestCorrectedProse:
    """Until Phase 3, corrected_prose echoes the original input."""

    @pytest.mark.asyncio
    async def test_valid_prose_echoed(self, momus, desert_state):
        prose = "The sand whispers secrets."
        result = await momus.validate_prose(prose, desert_state)
        assert result.corrected_prose == prose

    @pytest.mark.asyncio
    async def test_invalid_prose_still_echoed(self, momus, desert_state):
        prose = "The ocean waves crash around you."
        result = await momus.validate_prose(prose, desert_state)
        assert result.corrected_prose == prose  # not corrected yet (Phase 3)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestMomusValidationSchema:
    """MomusValidation pydantic model behaves correctly."""

    def test_default_valid(self):
        v = MomusValidation()
        assert v.valid is True
        assert v.hallucinations == []
        assert v.corrected_prose == ""

    def test_with_hallucinations(self):
        v = MomusValidation(
            valid=False,
            hallucinations=["Terrain mismatch", "Oath reference without oaths"],
            corrected_prose="Fixed prose here.",
        )
        assert v.valid is False
        assert len(v.hallucinations) == 2

    def test_serialization_roundtrip(self):
        v = MomusValidation(
            valid=False,
            hallucinations=["Error"],
            corrected_prose="Fixed.",
        )
        data = v.model_dump()
        v2 = MomusValidation(**data)
        assert v2.hallucinations == v.hallucinations


# ---------------------------------------------------------------------------
# Agent Identity
# ---------------------------------------------------------------------------

class TestAgentIdentity:
    def test_agent_name(self):
        m = Momus()
        assert m.name == "momus"
