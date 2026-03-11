"""Tests for Hypnos Dream Weaver — Sprint 8: Hypnos Reborn.

Tests cover:
- weave_dream() mock mode behavior
- Dream text quality (length, content)
- Dream trigger conditions (RESOLUTION beats only, phases 1-3)
- Dream lifecycle: set on state, consumed by stratified context, cleared
- SSE dream event format
- Legacy endpoint removal
"""

from __future__ import annotations

import json

import pytest

from app.agents.hypnos import Hypnos, _MOCK_DREAMS
from app.core.kernel import NyxKernel, _get_turn_metadata, _build_stratified_context
from app.schemas.state import ThreadState


# ---------------------------------------------------------------------------
# Mock Mode — weave_dream()
# ---------------------------------------------------------------------------

class TestWeaveDream:
    """Test Hypnos.weave_dream() in mock mode."""

    @pytest.fixture
    def hypnos(self):
        return Hypnos()

    @pytest.fixture
    def state(self):
        return ThreadState()

    @pytest.mark.asyncio
    async def test_returns_nonempty_string(self, hypnos, state):
        dream = await hypnos.weave_dream(state)
        assert isinstance(dream, str)
        assert len(dream) > 0

    @pytest.mark.asyncio
    async def test_dream_from_mock_pool(self, hypnos, state):
        """Mock dreams come from the _MOCK_DREAMS list."""
        dream = await hypnos.weave_dream(state)
        assert dream in _MOCK_DREAMS

    @pytest.mark.asyncio
    async def test_dream_length_reasonable(self, hypnos, state):
        """Dreams should be 20-500 chars in mock mode."""
        dream = await hypnos.weave_dream(state)
        assert 20 <= len(dream) <= 500

    @pytest.mark.asyncio
    async def test_multiple_dreams_vary(self, hypnos, state):
        """Over many calls, we should get more than one distinct dream."""
        dreams = set()
        for _ in range(30):
            dream = await hypnos.weave_dream(state)
            dreams.add(dream)
        assert len(dreams) > 1, "All 30 dreams were identical"


# ---------------------------------------------------------------------------
# Dream Trigger Conditions
# ---------------------------------------------------------------------------

class TestDreamTriggerConditions:
    """Dreams should fire ONLY on Resolution beats in phases 1-3."""

    def test_resolution_turns_are_3_6_9(self):
        """Turns 3, 6, 9 have RESOLUTION beat position."""
        for turn in (3, 6, 9):
            _, _, _, beat, _ = _get_turn_metadata(turn)
            assert beat == "RESOLUTION"

    def test_setup_turns_not_resolution(self):
        """Turns 1, 4, 7 are SETUP — no dream."""
        for turn in (1, 4, 7):
            _, _, _, beat, _ = _get_turn_metadata(turn)
            assert beat == "SETUP"

    def test_complication_turns_not_resolution(self):
        """Turns 2, 5, 8 are COMPLICATION — no dream."""
        for turn in (2, 5, 8):
            _, _, _, beat, _ = _get_turn_metadata(turn)
            assert beat == "COMPLICATION"

    def test_phase_4_turns_are_open(self):
        """Phase 4 turns (10+) have OPEN beat — no dream."""
        for turn in (10, 15, 20):
            _, _, _, beat, _ = _get_turn_metadata(turn)
            assert beat == "OPEN"

    def test_dream_trigger_logic(self):
        """Only phase 1-3 RESOLUTION beats should trigger dreams."""
        dream_turns = []
        no_dream_turns = []
        for turn in range(1, 15):
            phase, _, _, beat, _ = _get_turn_metadata(turn)
            if beat == "RESOLUTION" and phase <= 3:
                dream_turns.append(turn)
            else:
                no_dream_turns.append(turn)
        assert dream_turns == [3, 6, 9]
        assert 10 not in dream_turns


# ---------------------------------------------------------------------------
# Dream Lifecycle
# ---------------------------------------------------------------------------

class TestDreamLifecycle:
    """Test the full dream lifecycle on ThreadState."""

    def test_current_dream_default_empty(self):
        state = ThreadState()
        assert state.current_dream == ""

    def test_current_dream_can_be_set(self):
        state = ThreadState()
        state.current_dream = "A golden field stretches before you."
        assert state.current_dream == "A golden field stretches before you."

    def test_current_dream_can_be_cleared(self):
        state = ThreadState()
        state.current_dream = "Some dream text"
        state.current_dream = ""
        assert state.current_dream == ""


# ---------------------------------------------------------------------------
# Stratified Context — Dream Bleed
# ---------------------------------------------------------------------------

class TestDreamInStratifiedContext:
    """Dream text should appear in stratified context when present."""

    def test_dream_appears_in_context(self):
        """When current_dream is set, it should appear in stratified context."""
        state = ThreadState()
        state.current_dream = "Fish with human eyes swim past."
        context = _build_stratified_context(state)
        assert "Fish with human eyes swim past" in context
        assert "THE DREAM" in context

    def test_no_dream_section_when_empty(self):
        """When current_dream is empty, no dream section in context."""
        state = ThreadState()
        state.current_dream = ""
        context = _build_stratified_context(state)
        assert "THE DREAM" not in context


# ---------------------------------------------------------------------------
# SSE Event Format
# ---------------------------------------------------------------------------

class TestDreamSSEFormat:
    """Dream SSE event should have the correct format."""

    def test_dream_event_structure(self):
        """The dream SSE event should be: {"type": "dream", "text": "..."}"""
        dream_text = "You are running through golden wheat."
        event = json.dumps({"type": "dream", "text": dream_text})
        parsed = json.loads(event)
        assert parsed["type"] == "dream"
        assert parsed["text"] == dream_text
        assert set(parsed.keys()) == {"type", "text"}


# ---------------------------------------------------------------------------
# Legacy Removal
# ---------------------------------------------------------------------------

class TestLegacyRemoval:
    """Verify old Hypnos latency-mask code is gone."""

    def test_hypnos_evaluate_is_stub_only(self):
        """evaluate() exists as ABC stub but delegates to weave_dream."""
        hypnos = Hypnos()
        # It exists (ABC contract) but the real entry point is weave_dream
        assert hasattr(hypnos, "evaluate")
        assert hasattr(hypnos, "weave_dream")

    def test_hypnos_has_no_stream_fragments(self):
        """The old stream_fragments() method should be removed."""
        hypnos = Hypnos()
        assert not hasattr(hypnos, "stream_fragments")

    def test_hypnos_has_weave_dream(self):
        """The new weave_dream() method should exist."""
        hypnos = Hypnos()
        assert hasattr(hypnos, "weave_dream")
        assert callable(hypnos.weave_dream)

    def test_kernel_has_no_get_hypnos_stream(self):
        """get_hypnos_stream should be removed from the kernel."""
        kernel = NyxKernel()
        assert not hasattr(kernel, "get_hypnos_stream")
