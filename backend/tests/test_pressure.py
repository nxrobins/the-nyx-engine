"""Tests for the Phase 3 pressure economy and trigger rewrites."""

from __future__ import annotations

import pytest

from app.agents.clotho import _build_payload
from app.agents.eris import Eris
from app.agents.nemesis import Nemesis
from app.core.resolver import ResolvedOutcome
from app.schemas.state import PressureState, ThreadState
from app.services.pressure import apply_pressure_delta, evolve_pressures


class TestPressureEvolution:
    """World pressure should accumulate from action patterns and calm streaks."""

    def test_violent_public_action_increases_suspicion_and_wounds(self, fresh_state: ThreadState):
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I attack and shout at the crowd", outcome)
        assert evolution.delta["suspicion"] > 0
        assert evolution.delta["wounds"] > 0
        assert evolution.stable_turn is False

    def test_stable_turn_increments_stability_streak(self, fresh_state: ThreadState):
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I wait and observe", outcome)
        updated = apply_pressure_delta(
            fresh_state.pressures,
            evolution.delta,
            stable_turn=evolution.stable_turn,
        )
        assert evolution.stable_turn is True
        assert updated.stability_streak == 1

    def test_clotho_payload_demands_pressure_response(self, fresh_state: ThreadState):
        fresh_state.pressures = PressureState(suspicion=2.0)
        payload = _build_payload(fresh_state, "wait", epoch_phase=1)
        assert "At least one choice must answer active external pressure" in payload
        assert "Answer suspicion" in payload


class TestOmenRecedes:
    """Fate Recedes — omen must be able to fall, not only ratchet up.

    The player-facing layer already promises a fade ("Follow the omen before
    it fades"); these tests pin that the deterministic math now honours it,
    while keeping fate's forgetfulness slow enough that a single fateful event
    still raises omen on its own turn.
    """

    def test_omen_fades_on_a_quiet_turn(self, fresh_state: ThreadState):
        fresh_state.pressures = PressureState(omen=2.0)
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I wait and watch the road", outcome)
        assert evolution.stable_turn is True
        assert evolution.delta["omen"] < 0
        updated = apply_pressure_delta(
            fresh_state.pressures, evolution.delta, stable_turn=evolution.stable_turn
        )
        assert updated.omen < 2.0

    def test_omen_does_not_fade_on_a_turbulent_turn(self, fresh_state: ThreadState):
        fresh_state.pressures = PressureState(omen=2.0)
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I attack and shout at the crowd", outcome)
        assert evolution.stable_turn is False
        # No quiet-turn relief on a loud turn — fate keeps watching.
        assert evolution.delta.get("omen", 0.0) >= 0.0

    def test_a_fresh_omen_spike_still_nets_a_rise_even_when_quiet(
        self, fresh_state: ThreadState
    ):
        # A Nemesis strike adds omen on the same turn the fade would apply;
        # the spike must dominate so the warning is never silently erased.
        fresh_state.pressures = PressureState(omen=1.0)
        outcome = ResolvedOutcome(state=fresh_state, nemesis_struck=True)
        evolution = evolve_pressures(fresh_state, "I wait", outcome)
        assert evolution.delta["omen"] > 0

    def test_omen_never_underflows_below_zero(self, fresh_state: ThreadState):
        # At the floor, repeated quiet turns clamp at 0 — no negative omen.
        fresh_state.pressures = PressureState(omen=0.0)
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I wait and rest", outcome)
        updated = apply_pressure_delta(
            fresh_state.pressures, evolution.delta, stable_turn=evolution.stable_turn
        )
        assert updated.omen == 0.0

    def test_fade_is_slow_a_single_quiet_turn_barely_dents_high_omen(
        self, fresh_state: ThreadState
    ):
        # Sustained quiet, not one calm breath, earns fate's inattention.
        fresh_state.pressures = PressureState(omen=8.0)
        outcome = ResolvedOutcome(state=fresh_state)
        evolution = evolve_pressures(fresh_state, "I wait quietly", outcome)
        updated = apply_pressure_delta(
            fresh_state.pressures, evolution.delta, stable_turn=evolution.stable_turn
        )
        assert 7.5 <= updated.omen < 8.0  # a dent, not a reset


class TestPressureDrivenAgents:
    """Nemesis and Eris should react to pressure, not only raw imbalance."""

    @pytest.mark.asyncio
    async def test_nemesis_punishes_exploit_pattern(self, fresh_state: ThreadState, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "nemesis_model", "mock")
        fresh_state.pressures = PressureState(exploit_score=2.5)
        result = await Nemesis().evaluate(fresh_state, "look around")
        assert result.intervene is True
        assert result.intervention_type == "punishment"

    @pytest.mark.asyncio
    async def test_eris_targets_brittle_stability(self, fresh_state: ThreadState, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "eris_model", "mock")
        fresh_state.pressures = PressureState(stability_streak=6)
        monkeypatch.setattr("app.agents.eris.random.random", lambda: 0.6)
        result = await Eris().evaluate(fresh_state, "wait")
        assert result.chaos_triggered is True
