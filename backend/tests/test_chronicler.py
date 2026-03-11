"""Tests for Chronicler — the dual-track memory compression agent v2.0.

Covers: mock-mode evaluation, empty prose handling, _dominant helper,
mock chronicle quality, kernel trigger integration patterns,
dual-track output (mythic + factual), factual digest builder,
and schema validation.
"""

from __future__ import annotations

import pytest

from app.agents.chronicler import (
    CHRONICLER_SYSTEM_PROMPT,
    Chronicler,
    _build_factual_digest,
    _dominant,
    _MOCK_CHRONICLES,
)
from app.schemas.state import (
    ChroniclerResponse,
    Oath,
    SessionData,
    SoulLedger,
    SoulVectors,
    TheLoom,
    ThreadState,
)


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


@pytest.fixture
def rich_state() -> ThreadState:
    """A state with oaths, prophecy, and non-default vectors for digest tests."""
    return ThreadState(
        session=SessionData(
            turn_count=10,
            epoch_phase=3,
            current_environment="A blood-soaked arena under a bruised sky.",
        ),
        soul_ledger=SoulLedger(
            hamartia="Wrath of the Untempered",
            vectors=SoulVectors(metis=4.0, bia=8.5, kleos=6.0, aidos=3.0),
            active_oaths=[
                Oath(oath_id="o1", text="I swear to avenge my brother.", turn_sworn=3),
                Oath(oath_id="o2", text="I will protect the weak.", turn_sworn=7),
            ],
        ),
        the_loom=TheLoom(
            current_prophecy="The blade you sharpen will find your throat.",
        ),
    )


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
    """When prose_window is None or empty, Chronicler returns empty for both tracks."""

    @pytest.mark.asyncio
    async def test_none_prose_returns_empty(self, chronicler, fresh_state):
        result = await chronicler.evaluate(fresh_state, "idle", prose_window=None)
        assert result.chronicle_sentence == ""
        assert result.factual_digest == ""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, chronicler, fresh_state):
        result = await chronicler.evaluate(fresh_state, "idle", prose_window=[])
        assert result.chronicle_sentence == ""
        assert result.factual_digest == ""

    @pytest.mark.asyncio
    async def test_none_is_default(self, chronicler, fresh_state):
        """Omitting prose_window entirely should return empty."""
        result = await chronicler.evaluate(fresh_state, "idle")
        assert result.chronicle_sentence == ""
        assert result.factual_digest == ""


# ---------------------------------------------------------------------------
# Dual-Track Output
# ---------------------------------------------------------------------------

class TestDualTrackOutput:
    """Both mythic and factual tracks are produced simultaneously."""

    @pytest.mark.asyncio
    async def test_both_tracks_present(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert result.chronicle_sentence != ""
        assert result.factual_digest != ""

    @pytest.mark.asyncio
    async def test_mythic_track_from_mock(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert result.chronicle_sentence in _MOCK_CHRONICLES

    @pytest.mark.asyncio
    async def test_factual_track_is_deterministic(self, chronicler, fresh_state, sample_prose_window):
        """Same state + same window → same factual digest."""
        r1 = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        r2 = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert r1.factual_digest == r2.factual_digest

    @pytest.mark.asyncio
    async def test_factual_contains_setting(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        # fresh_state has "A shadowed threshold between worlds."
        assert "Setting:" in result.factual_digest

    @pytest.mark.asyncio
    async def test_factual_contains_dominant(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert "Dominant:" in result.factual_digest

    @pytest.mark.asyncio
    async def test_factual_contains_epoch(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert "Epoch:" in result.factual_digest

    @pytest.mark.asyncio
    async def test_factual_contains_turn_count(self, chronicler, fresh_state, sample_prose_window):
        result = await chronicler.evaluate(fresh_state, "walk", sample_prose_window)
        assert "Turns compressed: 5" in result.factual_digest


# ---------------------------------------------------------------------------
# Factual Digest Builder (unit tests)
# ---------------------------------------------------------------------------

class TestFactualDigestBuilder:
    """_build_factual_digest() produces correct deterministic output."""

    def test_fresh_state_basic(self, fresh_state):
        digest = _build_factual_digest(fresh_state, ["p1", "p2", "p3"])
        assert "Setting:" in digest
        assert "Dominant:" in digest
        assert "Epoch: 1" in digest
        assert "Turns compressed: 3" in digest

    def test_rich_state_has_oaths(self, rich_state):
        digest = _build_factual_digest(rich_state, ["p1"] * 5)
        assert "Oaths:" in digest
        assert "avenge" in digest

    def test_rich_state_has_prophecy(self, rich_state):
        digest = _build_factual_digest(rich_state, ["p1"] * 5)
        assert "Prophecy:" in digest
        assert "blade" in digest

    def test_rich_state_has_hamartia(self, rich_state):
        digest = _build_factual_digest(rich_state, ["p1"])
        assert "Flaw: Wrath of the Untempered" in digest

    def test_dominant_vector_bia(self, rich_state):
        digest = _build_factual_digest(rich_state, ["p1"])
        assert "Dominant: bia (8.5)" in digest

    def test_no_oaths_no_oath_field(self, fresh_state):
        digest = _build_factual_digest(fresh_state, ["p1"])
        assert "Oaths:" not in digest

    def test_no_prophecy_no_prophecy_field(self, fresh_state):
        digest = _build_factual_digest(fresh_state, ["p1"])
        assert "Prophecy:" not in digest

    def test_environment_truncation(self):
        """Very long environments are truncated to 80 chars."""
        state = ThreadState(
            session=SessionData(current_environment="A" * 200),
        )
        digest = _build_factual_digest(state, ["p1"])
        # The setting portion should be truncated
        setting_part = digest.split("|")[0].strip()
        assert len(setting_part) < 100

    def test_oaths_capped_at_three(self):
        """Only first 3 oaths appear even if more exist."""
        state = ThreadState(
            soul_ledger=SoulLedger(
                active_oaths=[
                    Oath(oath_id=f"o{i}", text=f"Oath {i}", turn_sworn=i)
                    for i in range(5)
                ],
            ),
        )
        digest = _build_factual_digest(state, ["p1"])
        # Should mention oaths but not all 5
        assert "Oath 0" in digest
        assert "Oath 2" in digest
        assert "Oath 4" not in digest

    def test_pipe_separated_format(self, rich_state):
        """Digest fields are separated by ' | '."""
        digest = _build_factual_digest(rich_state, ["p1"])
        assert " | " in digest
        parts = digest.split(" | ")
        assert len(parts) >= 4  # Setting, Dominant, Flaw, Oaths, Prophecy, Epoch, Turns


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
            inner = s[:-1]
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
    """ChroniclerResponse pydantic model behaves correctly (dual-track)."""

    def test_default_empty_sentence(self):
        r = ChroniclerResponse()
        assert r.chronicle_sentence == ""

    def test_default_empty_factual(self):
        r = ChroniclerResponse()
        assert r.factual_digest == ""

    def test_custom_sentence(self):
        r = ChroniclerResponse(chronicle_sentence="The Soul learned fire has a price.")
        assert "price" in r.chronicle_sentence

    def test_custom_factual(self):
        r = ChroniclerResponse(factual_digest="Setting: A cave | Dominant: metis (7.0)")
        assert "metis" in r.factual_digest

    def test_both_tracks_set(self):
        r = ChroniclerResponse(
            chronicle_sentence="The thread frayed.",
            factual_digest="Setting: arena | Dominant: bia (9.0)",
        )
        assert r.chronicle_sentence == "The thread frayed."
        assert "bia" in r.factual_digest

    def test_serialization_roundtrip(self):
        r = ChroniclerResponse(
            chronicle_sentence="The thread frayed.",
            factual_digest="Setting: cave | Dominant: aidos (6.0)",
        )
        data = r.model_dump()
        r2 = ChroniclerResponse(**data)
        assert r2.chronicle_sentence == r.chronicle_sentence
        assert r2.factual_digest == r.factual_digest

    def test_serialization_includes_factual(self):
        r = ChroniclerResponse(factual_digest="Epoch: 3 | Turns: 5")
        data = r.model_dump()
        assert "factual_digest" in data
        assert data["factual_digest"] == "Epoch: 3 | Turns: 5"


# ---------------------------------------------------------------------------
# ThreadState factual_chronicle field
# ---------------------------------------------------------------------------

class TestThreadStateFactualChronicle:
    """ThreadState.factual_chronicle stores factual track data."""

    def test_default_empty(self):
        state = ThreadState()
        assert state.factual_chronicle == []

    def test_append_factual(self):
        state = ThreadState()
        state.factual_chronicle.append("Setting: cave | Dominant: metis (7.0)")
        assert len(state.factual_chronicle) == 1
        assert "metis" in state.factual_chronicle[0]

    def test_parallel_to_chronicle(self):
        """Both tracks can grow independently."""
        state = ThreadState()
        state.chronicle.append("The Soul walked into shadow.")
        state.factual_chronicle.append("Setting: shadow | Dominant: aidos (6.0)")
        assert len(state.chronicle) == 1
        assert len(state.factual_chronicle) == 1

    def test_serialization_roundtrip(self):
        state = ThreadState(
            chronicle=["Mythic sentence."],
            factual_chronicle=["Setting: cave | Epoch: 2"],
        )
        data = state.model_dump()
        state2 = ThreadState(**data)
        assert state2.chronicle == ["Mythic sentence."]
        assert state2.factual_chronicle == ["Setting: cave | Epoch: 2"]
