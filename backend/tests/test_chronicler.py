"""Tests for Chronicler — the recursive memory compression agent.

Covers: mock-mode evaluation, empty prose handling, _dominant helper,
mock chronicle quality, kernel trigger integration patterns.
"""

from __future__ import annotations

import pytest

from app.agents.chronicler import (
    CHRONICLER_SYSTEM_PROMPT,
    Chronicler,
    _dominant,
    _MOCK_CHRONICLES,
)
from app.schemas.state import ChroniclerResponse, SoulVectors, ThreadState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chronicler(monkeypatch) -> Chronicler:
    """A Chronicler agent pinned to mock mode."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "chronicler_model", "mock")
    return Chronicler()


@pytest.fixture
def sample_prose_window() -> list[str]:
    """5 turns of representative prose for compression."""
    return [
        "The child stumbled into the arena, sand biting at bare feet.",
        "A guard lunged — the child twisted sideways, knife flashing once.",
        "Blood on stone. The crowd roared, but the child heard only silence.",
        "The merchant's offer hung in the air: safety, in exchange for a name.",
        "The child refused, stepping back into the dust and the heat.",
    ]


@pytest.fixture
def short_prose_window() -> list[str]:
    """Only 2 turns — below the normal 5-turn interval."""
    return [
        "Dawn broke over the ruins.",
        "The child picked through rubble for anything useful.",
    ]


# ---------------------------------------------------------------------------
# Mock Mode Evaluation
# ---------------------------------------------------------------------------

class TestMockEvaluation:
    """Chronicler in mock mode returns valid pre-baked sentences."""

    @pytest.mark.asyncio
    async def test_returns_chronicler_response(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk forward", sample_prose_window)
        assert isinstance(result, ChroniclerResponse)

    @pytest.mark.asyncio
    async def test_sentence_from_mock_list(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk forward", sample_prose_window)
        assert result.chronicle_sentence in _MOCK_CHRONICLES

    @pytest.mark.asyncio
    async def test_sentence_is_nonempty(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk forward", sample_prose_window)
        assert len(result.chronicle_sentence) > 20

    @pytest.mark.asyncio
    async def test_short_window_still_works(self, chronicler, fresh_state, short_prose_window):
        """Even < 5 turns of prose should produce a result."""
        result = await chronicler.evaluate(fresh_state, "search", short_prose_window)
        assert result.chronicle_sentence in _MOCK_CHRONICLES

    @pytest.mark.asyncio
    async def test_single_turn_window(self, chronicler, fresh_state):
        """A single-element prose window is valid input."""
        result = await chronicler.evaluate(fresh_state, "look", ["The child opened their eyes."])
        assert result.chronicle_sentence != ""


# ---------------------------------------------------------------------------
# Empty / None Prose Window
# ---------------------------------------------------------------------------

class TestEmptyProse:
    """When prose_window is None or empty, Chronicler returns an empty sentence."""

    @pytest.mark.asyncio
    async def test_none_prose_returns_empty(self, chronicler, fresh_state):
        result = await chronicler.evaluate(fresh_state, "idle", prose_window=None)
        assert result.chronicle_sentence == ""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, chronicler, fresh_state):
        result = await chronicler.evaluate(fresh_state, "idle", prose_window=[])
        assert result.chronicle_sentence == ""

    @pytest.mark.asyncio
    async def test_none_is_default(self, chronicler, fresh_state):
        """Omitting prose_window entirely should return empty."""
        result = await chronicler.evaluate(fresh_state, "idle")
        assert result.chronicle_sentence == ""


# ---------------------------------------------------------------------------
# _dominant() helper
# ---------------------------------------------------------------------------

class TestDominantHelper:
    """_dominant() returns the name of the highest soul vector."""

    def test_metis_dominant(self):
        state = ThreadState(
            soul_ledger={"vectors": SoulVectors(metis=9.0, bia=3.0, kleos=4.0, aidos=2.0)}
        )
        assert _dominant(state) == "metis"

    def test_bia_dominant(self):
        state = ThreadState(
            soul_ledger={"vectors": SoulVectors(metis=3.0, bia=9.0, kleos=4.0, aidos=2.0)}
        )
        assert _dominant(state) == "bia"

    def test_kleos_dominant(self):
        state = ThreadState(
            soul_ledger={"vectors": SoulVectors(metis=3.0, bia=4.0, kleos=9.0, aidos=2.0)}
        )
        assert _dominant(state) == "kleos"

    def test_aidos_dominant(self):
        state = ThreadState(
            soul_ledger={"vectors": SoulVectors(metis=3.0, bia=4.0, kleos=2.0, aidos=9.0)}
        )
        assert _dominant(state) == "aidos"

    def test_balanced_returns_first_max(self):
        """With all equal vectors, max() returns the first encountered."""
        state = ThreadState()  # defaults: all 5.0
        result = _dominant(state)
        assert result in ("metis", "bia", "kleos", "aidos")


# ---------------------------------------------------------------------------
# Mock Chronicle Quality
# ---------------------------------------------------------------------------

class TestMockChronicleQuality:
    """Pre-baked mock chronicles meet the Chronicler's literary standards."""

    def test_all_end_with_period(self):
        for s in _MOCK_CHRONICLES:
            assert s.endswith("."), f"Chronicle doesn't end with period: {s!r}"

    def test_all_are_single_sentences(self):
        """No chronicle should contain multiple sentence-ending punctuation."""
        for s in _MOCK_CHRONICLES:
            # Strip final period, check no other sentence-enders remain
            inner = s[:-1]
            # Allow em-dashes and commas, but not multiple periods
            period_count = inner.count(".")
            assert period_count == 0, f"Chronicle has multiple sentences: {s!r}"

    def test_all_contain_child_or_soul(self):
        """Each mock chronicle should reference 'The Child' or 'The Soul'."""
        for s in _MOCK_CHRONICLES:
            assert "The Child" in s or "The Soul" in s, (
                f"Chronicle missing 'The Child'/'The Soul': {s!r}"
            )

    def test_all_substantial_length(self):
        """Each chronicle should be at least 40 characters."""
        for s in _MOCK_CHRONICLES:
            assert len(s) >= 40, f"Chronicle too short ({len(s)} chars): {s!r}"

    def test_no_duplicates(self):
        assert len(_MOCK_CHRONICLES) == len(set(_MOCK_CHRONICLES))

    def test_at_least_eight_entries(self):
        """Enough variety for mock mode not to feel repetitive."""
        assert len(_MOCK_CHRONICLES) >= 8


# ---------------------------------------------------------------------------
# System Prompt Loaded
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """The Chronicler's system prompt loads correctly from YAML."""

    def test_prompt_loaded(self):
        assert isinstance(CHRONICLER_SYSTEM_PROMPT, str)
        assert len(CHRONICLER_SYSTEM_PROMPT) > 50

    def test_prompt_mentions_compression(self):
        assert "single mythic sentence" in CHRONICLER_SYSTEM_PROMPT

    def test_prompt_starts_with_identity(self):
        assert CHRONICLER_SYSTEM_PROMPT.startswith("You are ")


# ---------------------------------------------------------------------------
# Agent Identity
# ---------------------------------------------------------------------------

class TestAgentIdentity:
    def test_agent_name(self):
        c = Chronicler()
        assert c.name == "chronicler"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestChroniclerResponseSchema:
    """ChroniclerResponse pydantic model behaves correctly."""

    def test_default_empty_sentence(self):
        r = ChroniclerResponse()
        assert r.chronicle_sentence == ""

    def test_custom_sentence(self):
        r = ChroniclerResponse(chronicle_sentence="The Soul learned fire has a price.")
        assert "price" in r.chronicle_sentence

    def test_serialization_roundtrip(self):
        r = ChroniclerResponse(chronicle_sentence="The thread frayed.")
        data = r.model_dump()
        r2 = ChroniclerResponse(**data)
        assert r2.chronicle_sentence == r.chronicle_sentence
