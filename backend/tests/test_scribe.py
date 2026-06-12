"""Scribe tests — the gate, the mock biographer, and the failure posture."""

from __future__ import annotations

import pytest

from app.agents.scribe import Scribe
from app.schemas.book import ScribeSnapshot
from app.services.scribe_gate import gate_chapter


def _snapshot(**overrides) -> ScribeSnapshot:
    payload = dict(
        thread_stamp="test:1",
        epoch_index=1,
        epoch_name="The Hearth",
        covers_turns=(1, 3),
        boundary_turn=3,
        prose_window=[
            "Maren worked the tallow while the wind tested the door.",
            "Kael came home grey with dust and said nothing at supper.",
            "Orin hid the black stone where the floorboard lifted.",
        ],
        factual_chronicle=["Turn 3: Orin hid the black stone from Torval."],
        chronicle=["The Child learned that silence has teeth."],
        life_voice="Short, percussive sentences. Heat and iron imagery.",
        player_name="Orin",
        player_age=5,
        hamartia="Wrath of the Untempered",
        settlement="Ashfall",
        npc_names=["Maren", "Kael", "Torval"],
    )
    payload.update(overrides)
    return ScribeSnapshot(**payload)


class TestGateChapter:
    def test_grounded_chapter_passes(self):
        prose = (
            "In Ashfall the winters were counted in candle stubs. Maren worked "
            "the piles while Kael said less each season, and Orin learned the "
            "weight of things that must be hidden."
        )
        assert gate_chapter(prose, _snapshot()) == []

    def test_anachronism_rejected(self):
        prose = (
            "In Ashfall, Maren checked her telephone while the ore carts "
            "rolled past the gate in the grey morning light of the camp."
        )
        violations = gate_chapter(prose, _snapshot())
        assert any("anachronism" in v for v in violations)

    def test_mysticism_rejected(self):
        prose = (
            "In Ashfall the fabric of reality grew thin around Maren, and a "
            "threshold between worlds opened in the sorting shed that winter."
        )
        violations = gate_chapter(prose, _snapshot())
        assert any("mysticism" in v for v in violations)

    def test_ungrounded_biography_rejected(self):
        prose = (
            "Somewhere a child grew up among workers and dust, learning hard "
            "lessons in a hard place that could have been anywhere at all, "
            "told by no one in particular."
        )
        violations = gate_chapter(prose, _snapshot())
        assert any("names nobody" in v for v in violations)

    def test_too_short_rejected(self):
        violations = gate_chapter("Ashfall was cold.", _snapshot())
        assert any("length" in v for v in violations)


class TestMockScribe:
    @pytest.mark.asyncio
    async def test_mock_drafts_valid_chapter(self):
        chapter = await Scribe().draft_chapter(_snapshot())
        assert chapter is not None
        assert chapter.epoch_index == 1
        assert chapter.covers_turns == (1, 3)
        assert chapter.thread_stamp == "test:1"
        assert "Ashfall" in chapter.prose
        assert chapter.title == "Chapter 1: The Hearth"

    @pytest.mark.asyncio
    async def test_mock_is_deterministic(self):
        a = await Scribe().draft_chapter(_snapshot())
        b = await Scribe().draft_chapter(_snapshot())
        assert a == b

    @pytest.mark.asyncio
    async def test_final_chapter_carries_death_and_epitaph(self):
        snap = _snapshot(
            epoch_index=3,
            covers_turns=(7, 7),
            boundary_turn=7,
            death_reason="The shaft took him as it took the others.",
            epitaph="Here lies Orin, who struck first and asked the dark for nothing.",
        )
        chapter = await Scribe().draft_chapter(snap)
        assert chapter is not None
        assert chapter.title == "Chapter 3: The Severing"
        assert "the thread ended" in chapter.prose
        assert "Here lies Orin" in chapter.prose

    @pytest.mark.asyncio
    async def test_llm_mode_failure_returns_none(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "scribe_model", "anthropic/whatever")

        async def mystical(**kwargs):
            return (
                "In Ashfall the fabric of reality came apart around Maren "
                "and a threshold between worlds swallowed the camp whole."
            )

        import app.agents.scribe as scribe_module
        monkeypatch.setattr(scribe_module.llm, "generate", mystical)

        chapter = await Scribe().draft_chapter(_snapshot())
        assert chapter is None  # both attempts gated out — the book is shorter
