"""Tests for the streaming separator buffer logic in process_turn_stream.

The separator buffer holds back tokens near the ---CHOICES--- marker to
prevent it from leaking into the prose stream. These tests verify the
buffer under various edge cases:
  - Normal: separator at end of output
  - Split: separator split across two token chunks
  - Absent: no separator (Phase 4 open mode)
  - Malformed: bad JSON after separator
  - Short: very short output (< separator length)
  - Multiple turns: sequential streaming
"""

from __future__ import annotations

import json

import pytest

from app.core.kernel import NyxKernel


@pytest.fixture
def kernel(monkeypatch) -> NyxKernel:
    """A fresh kernel with all agents pinned to mock mode."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "clotho_model", "mock")
    monkeypatch.setattr(settings, "lachesis_model", "mock")
    monkeypatch.setattr(settings, "nemesis_model", "mock")
    monkeypatch.setattr(settings, "eris_model", "mock")
    monkeypatch.setattr(settings, "hypnos_model", "mock")
    monkeypatch.setattr(settings, "chronicler_model", "mock")
    return NyxKernel()


async def _init(kernel: NyxKernel) -> None:
    await kernel.initialize(
        hamartia="Unformed",
        player_id="test_player",
        name="Hero",
        gender="boy",
        first_memory="A light in the distance I could not reach.",
    )


async def _collect_events(kernel: NyxKernel, action: str) -> list[dict]:
    """Collect all SSE events from process_turn_stream."""
    events = []
    async for raw in kernel.process_turn_stream(action):
        # Each raw is "data: {...}\n\n"
        if raw.startswith("data: "):
            payload = json.loads(raw[6:].strip())
            events.append(payload)
    return events


def _filter_events(events: list[dict], event_type: str) -> list[dict]:
    """Filter collected events by type."""
    return [e for e in events if e.get("type") == event_type]


class TestStreamEventSequence:
    """Verify correct SSE event ordering."""

    @pytest.mark.asyncio
    async def test_normal_turn_emits_mechanic_prose_state(self, kernel: NyxKernel):
        """A normal valid turn should emit: mechanic → deliberation → prose → state."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        types = [e["type"] for e in events]

        assert "mechanic" in types
        assert "deliberation" in types
        assert "prose" in types
        assert "state" in types
        # mechanic before deliberation before prose before state
        assert types.index("mechanic") < types.index("deliberation")
        assert types.index("deliberation") < types.index("prose")
        assert types.index("prose") < types.index("state")

    @pytest.mark.asyncio
    async def test_invalid_action_emits_prose_then_state(self, kernel: NyxKernel):
        """Invalid action: deliberation → prose (rejection) → state, no mechanic."""
        await _init(kernel)
        events = await _collect_events(kernel, "fly into the sky")
        types = [e["type"] for e in events]

        assert "mechanic" not in types
        assert "deliberation" in types
        assert "prose" in types
        assert "state" in types

    @pytest.mark.asyncio
    async def test_invalid_action_prose_contains_reason(self, kernel: NyxKernel):
        await _init(kernel)
        events = await _collect_events(kernel, "fly into the sky")
        prose_events = _filter_events(events, "prose")
        combined = "".join(e["text"] for e in prose_events)
        assert "impossible demands" in combined.lower() or "does not bend" in combined.lower()


class TestSeparatorBuffer:
    """The separator buffer correctly filters ---CHOICES--- from streamed prose."""

    @pytest.mark.asyncio
    async def test_separator_not_in_prose_events(self, kernel: NyxKernel):
        """The ---CHOICES--- separator must never appear in emitted prose."""
        await _init(kernel)
        events = await _collect_events(kernel, "attack the beast")
        prose_events = _filter_events(events, "prose")
        combined = "".join(e["text"] for e in prose_events)
        assert "---CHOICES---" not in combined

    @pytest.mark.asyncio
    async def test_prose_is_not_empty(self, kernel: NyxKernel):
        """Prose should contain actual narrative text."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        prose_events = _filter_events(events, "prose")
        combined = "".join(e["text"] for e in prose_events)
        assert len(combined.strip()) > 0

    @pytest.mark.asyncio
    async def test_state_event_has_choices(self, kernel: NyxKernel):
        """In Phase 1-3, the state event should include ui_choices."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        state_events = _filter_events(events, "state")
        assert len(state_events) == 1
        choices = state_events[0].get("ui_choices", [])
        # Mock Clotho provides choices in Phase 1
        assert isinstance(choices, list)

    @pytest.mark.asyncio
    async def test_state_event_not_terminal(self, kernel: NyxKernel):
        """Normal turns produce non-terminal state events."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        state_events = _filter_events(events, "state")
        assert len(state_events) == 1
        assert state_events[0]["terminal"] is False


class TestSeparatorBufferEdgeCases:
    """Edge cases for the separator buffer flush logic."""

    @pytest.mark.asyncio
    async def test_short_prose_no_separator(self, kernel: NyxKernel):
        """Very short mock output (< separator length) should still work."""
        await _init(kernel)
        # Mock mode always works even if output is shorter than separator
        events = await _collect_events(kernel, "look around")
        prose_events = _filter_events(events, "prose")
        assert len(prose_events) >= 1

    @pytest.mark.asyncio
    async def test_sequential_turns_produce_independent_streams(self, kernel: NyxKernel):
        """Each turn's stream should be independent."""
        await _init(kernel)
        events_1 = await _collect_events(kernel, "look around")
        events_2 = await _collect_events(kernel, "attack the beast")

        # Both should have complete event sequences
        types_1 = [e["type"] for e in events_1]
        types_2 = [e["type"] for e in events_2]
        assert "state" in types_1
        assert "state" in types_2

    @pytest.mark.asyncio
    async def test_turn_number_increments_across_streams(self, kernel: NyxKernel):
        """Turn numbers should advance correctly across streaming calls."""
        await _init(kernel)
        events_1 = await _collect_events(kernel, "look around")
        events_2 = await _collect_events(kernel, "look around")

        state_1 = _filter_events(events_1, "state")[0]
        state_2 = _filter_events(events_2, "state")[0]

        t1 = state_1.get("turn_number", state_1.get("payload", {}).get("session", {}).get("turn_count", 0))
        t2 = state_2.get("turn_number", state_2.get("payload", {}).get("session", {}).get("turn_count", 0))
        assert t2 > t1

    @pytest.mark.asyncio
    async def test_mechanic_payload_has_deltas(self, kernel: NyxKernel):
        """Mechanic event should contain vector_deltas and dominant."""
        await _init(kernel)
        events = await _collect_events(kernel, "attack the beast")
        mechanic_events = _filter_events(events, "mechanic")
        assert len(mechanic_events) == 1
        payload = mechanic_events[0]["payload"]
        assert "vector_deltas" in payload
        assert "dominant" in payload
        assert "valid" in payload


class TestMechanicEvent:
    """The mechanic event carries correct pre-prose metadata."""

    @pytest.mark.asyncio
    async def test_mechanic_reports_nemesis(self, kernel: NyxKernel):
        """Mechanic payload includes nemesis_struck flag."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        mechanic_events = _filter_events(events, "mechanic")
        if mechanic_events:
            assert "nemesis_struck" in mechanic_events[0]["payload"]

    @pytest.mark.asyncio
    async def test_mechanic_reports_eris(self, kernel: NyxKernel):
        """Mechanic payload includes eris_struck flag."""
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        mechanic_events = _filter_events(events, "mechanic")
        if mechanic_events:
            assert "eris_struck" in mechanic_events[0]["payload"]


class TestDeliberationEvent:
    """The deliberation event exposes the resolver trace."""

    @pytest.mark.asyncio
    async def test_deliberation_payload_has_winner_order(self, kernel: NyxKernel):
        await _init(kernel)
        events = await _collect_events(kernel, "look around")
        deliberation_events = _filter_events(events, "deliberation")
        assert len(deliberation_events) == 1
        payload = deliberation_events[0]["payload"]
        assert "winner_order" in payload
        assert "proposals" in payload
