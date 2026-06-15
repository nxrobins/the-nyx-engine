"""The Vigil — Player Safety, Phase 1 (the pure-engineering floor).

Two safe, no-authored-crisis-content guarantees:
  * a self-destruction-keyword death is NON-miracleable (permanence), so a
    vulnerable player never gets a "the dice saved you" reprieve;
  * a typed self-destruction framing is REDACTED from every durable, world-
    readable store (log / DB / RAG), while the fiction's math is unperturbed.

The duty-of-care SURFACE (consent UI, crisis-resource copy, ideation detection
patterns, the welfare classifier) is deferred to human + clinical review (see
backend/SAFETY.md); it is not exercised here because it is not shipped here.
"""

from __future__ import annotations

import logging

import pytest

from app.core.resolver import ConflictResolver
from app.services.welfare import REDACTION_TOKEN, flags_sensitive_input
from app.schemas.state import (
    AtroposResponse,
    ErisResponse,
    LachesisResponse,
    NemesisResponse,
    SoulLedger,
    SoulVectors,
    ThreadState,
)


def _balanced_state() -> ThreadState:
    # imbalance 0 < nemesis_imbalance_threshold (6.0) → miracle-eligible
    return ThreadState(soul_ledger=SoulLedger(vectors=SoulVectors(metis=5, bia=5, kleos=5, aidos=5)))


def _resolve(atropos: AtroposResponse):
    state = _balanced_state()
    return ConflictResolver().resolve(
        state=state,
        lachesis=LachesisResponse(valid_action=True, updated_state=state),
        atropos=atropos,
        nemesis=NemesisResponse(intervene=False),
        eris=ErisResponse(chaos_triggered=True),  # a miracle WOULD fire if eligible
    )


class TestMiracleExemption:
    def test_self_destruction_death_is_never_miracled(self):
        out = _resolve(AtroposResponse(
            terminal_state=True,
            death_reason="You chose oblivion. The thread ends by your own hand.",
            self_destruction_origin=True,
        ))
        assert out.terminal is True                      # permanence — no reprieve
        assert "oblivion" in out.death_reason

    def test_ordinary_death_is_still_miracled_when_balanced(self):
        out = _resolve(AtroposResponse(
            terminal_state=True,
            death_reason="Your soul gutters like a candle in wind.",
            self_destruction_origin=False,
        ))
        assert out.terminal is False                     # the exemption is scoped, not blanket
        assert out.eris_struck is True


class TestSensitiveInput:
    def test_flags_self_destruction_framing(self):
        # Phase 2: the redaction key is now the unified crisis set — the
        # real-world-framed death phrases, NOT the purely-poetic ones.
        assert flags_sensitive_input("I will drink the poison tonight")
        assert flags_sensitive_input("i want to JUMP OFF the bridge")

    def test_does_not_flag_poetic_game_vocab(self):
        # "embrace the void" / "welcome oblivion" still END THE THREAD in the
        # fiction (atropos.py, unchanged) but are NOT real-world disclosures —
        # so they neither raise the care card nor are treated as sensitive.
        assert not flags_sensitive_input("I embrace the void forever")
        assert not flags_sensitive_input("I welcome oblivion")

    def test_does_not_flag_ordinary_play(self):
        assert not flags_sensitive_input("I help Sera with the harvest")
        assert not flags_sensitive_input("attack the guard")


class TestRedaction:
    @pytest.mark.asyncio
    async def test_self_harm_input_redacted_from_durable_stores(self, monkeypatch, caplog):
        import app.core.kernel as kmod

        captured: list[str] = []

        async def spy_create_turn(**kw):
            captured.append(kw.get("action"))

        monkeypatch.setattr(kmod, "create_turn", spy_create_turn)

        kernel = kmod.NyxKernel()
        rag_actions: list[str] = []
        real_add = kernel.rag.add_turn

        async def spy_add(**kw):
            rag_actions.append(kw.get("action"))
            return await real_add(**kw)

        monkeypatch.setattr(kernel.rag, "add_turn", spy_add)

        await kernel.initialize(
            hamartia="Hubris of the Intellect", player_id="vigil",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        captured.clear()
        rag_actions.clear()

        # A real-world-framed death phrase: BOTH a fiction death-trigger AND a
        # genuine disclosure, so it both severs the thread AND is redacted.
        phrase = "drink the poison"
        with caplog.at_level(logging.INFO):
            result = await kernel.process_turn(f"I {phrase} and end it all")

        # The fiction still read the real action: the self-chosen death fired.
        assert result.terminal is True
        assert "oblivion" in result.death_reason

        # The verbatim phrase leaked into NO durable/observable store.
        assert all(phrase not in (a or "") for a in captured), captured
        assert all(phrase not in (a or "") for a in rag_actions), rag_actions
        assert all(phrase not in record.getMessage() for record in caplog.records)

        # What WAS persisted is the redaction token.
        assert any(a == REDACTION_TOKEN for a in captured), captured

    @pytest.mark.asyncio
    async def test_ordinary_action_is_not_redacted(self, monkeypatch):
        import app.core.kernel as kmod

        captured: list[str] = []

        async def spy_create_turn(**kw):
            captured.append(kw.get("action"))

        monkeypatch.setattr(kmod, "create_turn", spy_create_turn)
        kernel = kmod.NyxKernel()
        await kernel.initialize(
            hamartia="Hubris of the Intellect", player_id="vigil2",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        captured.clear()
        await kernel.process_turn("help Sera with the harvest")
        assert any("help Sera" in (a or "") for a in captured)       # real action persisted
        assert all(a != REDACTION_TOKEN for a in captured)
