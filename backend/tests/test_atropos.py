"""Atropos behavioral coverage — the dead-soul trigger and the self-destruction
permanence stamp (audit S4 + S1).

Before this, Trigger 2 (dead soul) was exercised only as pure soul-math and the
self_destruction_origin flag only on hand-built AtroposResponses — never on the
real agent. These pin both, including the audit-S1 fix that a self-destruction
framing is non-miracleable no matter which trigger fires.
"""

from __future__ import annotations

from app.agents.atropos import Atropos
from app.core.config import settings
from app.schemas.state import SoulLedger, SoulVectors, ThreadState


def _state(vectors: SoulVectors) -> ThreadState:
    return ThreadState(soul_ledger=SoulLedger(vectors=vectors))


class TestDeadSoulTrigger:
    """A collapsed soul (all vectors <= 1.0) severs the thread (Trigger 2)."""

    async def test_dead_soul_severs_with_benign_action(self, dead_soul_vectors):
        out = await Atropos().evaluate(_state(dead_soul_vectors), "wait quietly")
        assert out.terminal_state is True
        assert "gutters" in out.death_reason
        # A NATURAL collapse via a benign action stays Eris-miracle-eligible:
        # the self-destruction stamp must NOT be set here, or we would silently
        # make ordinary soul-death permanent (a scoped-permanence violation).
        assert out.self_destruction_origin is False

    async def test_failing_but_not_dead_soul_is_only_a_warning(self):
        # All vectors <= 2.0 but not all <= 1.0: the Fates grow restless, but the
        # thread does not sever.
        out = await Atropos().evaluate(
            _state(SoulVectors(metis=2.0, bia=2.0, kleos=2.0, aidos=2.0)), "wait"
        )
        assert out.terminal_state is False


class TestSelfDestructionPermanence:
    """A self-destruction framing is non-miracleable NO MATTER which trigger
    fires (audit S1): the flag is computed once and stamped on every terminal
    return, not just the keyword branch."""

    async def test_keyword_alone_sets_the_flag(self):
        kw = settings.atropos_death_keywords[0]
        out = await Atropos().evaluate(_state(SoulVectors()), f"I {kw}")
        assert out.terminal_state is True
        assert out.self_destruction_origin is True

    async def test_dead_soul_plus_self_destruction_is_non_miracleable(self, dead_soul_vectors):
        # The bug: a self-destruction action coinciding with a collapsed soul
        # routes through Trigger 2 (dead soul, checked before the keyword trigger),
        # which left the flag False — so the resolver could Eris-miracle a
        # self-destruction death back to survival on a >=2% chaos roll.
        kw = settings.atropos_death_keywords[0]
        out = await Atropos().evaluate(_state(dead_soul_vectors), f"I {kw}")
        assert out.terminal_state is True
        assert "gutters" in out.death_reason        # routed via Trigger 2, not 3
        assert out.self_destruction_origin is True   # ...yet still permanent
