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
