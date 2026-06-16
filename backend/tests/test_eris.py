"""Eris chance clamp — the documented flaky-death root cause (audit S3).

`chance = max(0.02, min(chance, 0.9))` is why every death test in the suite must
pin `random()->0.999` (`eris_chaos_probability=0.0` alone does NOT silence Eris).
Nothing asserted the clamp itself, so a refactor lowering/removing the floor or
cap would pass green while silently re-arming the flaky-death class suite-wide.
These pin the floor, the cap, and the main bias terms directly.
"""

from __future__ import annotations

import app.agents.eris as eris_module
from app.agents.eris import Eris
from app.core.config import settings
from app.schemas.state import SoulLedger, SoulVectors, ThreadState


def _state(**pressures) -> ThreadState:
    st = ThreadState(soul_ledger=SoulLedger(vectors=SoulVectors()))
    for key, val in pressures.items():
        setattr(st.pressures, key, val)
    return st


def _pin(monkeypatch, roll: float) -> None:
    """Force the unseeded RNG to a fixed roll — the canonical Eris pin."""
    monkeypatch.setattr(eris_module.random, "random", lambda: roll)


class TestErisClamp:
    async def test_floor_holds_at_minimum_chance(self, monkeypatch):
        # No base probability, no bias: chance clamps UP to the 0.02 floor — so a
        # roll just under it still triggers (this is exactly why 0.0 can't silence
        # Eris). A roll just over the floor does not.
        monkeypatch.setattr(settings, "eris_chaos_probability", 0.0)
        _pin(monkeypatch, 0.01)
        assert (await Eris().evaluate(_state(), "wait")).chaos_triggered is True
        _pin(monkeypatch, 0.03)
        assert (await Eris().evaluate(_state(), "wait")).chaos_triggered is False

    async def test_cap_holds_at_maximum_chance(self, monkeypatch):
        # Push raw chance well past 1.0; it must clamp DOWN to 0.9, so a roll above
        # 0.9 still escapes. Without the cap, chance>1 would trigger on every roll.
        monkeypatch.setattr(settings, "eris_chaos_probability", 0.9)
        st = _state(stability_streak=10)  # +min(10*0.05,0.35)=0.35 -> raw >=1.25
        _pin(monkeypatch, 0.95)
        assert (await Eris().evaluate(st, "wait")).chaos_triggered is False
        _pin(monkeypatch, 0.85)
        assert (await Eris().evaluate(st, "wait")).chaos_triggered is True


class TestErisBias:
    async def test_stability_streak_raises_chance(self, monkeypatch):
        monkeypatch.setattr(settings, "eris_chaos_probability", 0.0)
        # streak 4 -> +0.20 streak bias +0.08 brittle bonus = 0.28. A 0.25 roll
        # triggers under tension; at baseline (streak 0 -> floor 0.02) it does not.
        _pin(monkeypatch, 0.25)
        assert (await Eris().evaluate(_state(stability_streak=0), "wait")).chaos_triggered is False
        assert (await Eris().evaluate(_state(stability_streak=4), "wait")).chaos_triggered is True

    async def test_brittle_bonus_withheld_while_exploiting(self, monkeypatch):
        monkeypatch.setattr(settings, "eris_chaos_probability", 0.0)
        # streak 2: +0.10 streak bias, plus +0.08 brittle ONLY when exploit<1.0.
        # honest -> 0.18, exploiting -> 0.10; a 0.13 roll separates them.
        _pin(monkeypatch, 0.13)
        honest = _state(stability_streak=2, exploit_score=0.0)
        exploiting = _state(stability_streak=2, exploit_score=2.0)
        assert (await Eris().evaluate(honest, "wait")).chaos_triggered is True
        assert (await Eris().evaluate(exploiting, "wait")).chaos_triggered is False
