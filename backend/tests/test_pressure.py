"""Tests for the Phase 3 pressure economy and trigger rewrites."""

from __future__ import annotations

import pytest

from app.agents.clotho import _build_payload
from app.agents.eris import Eris
from app.agents.nemesis import Nemesis
from app.core.resolver import ResolvedOutcome
from app.schemas.state import Oath, OathTerms, PressureState, SoulLedger, ThreadState
from app.services.pressure import (
    apply_pressure_delta,
    evolve_pressures,
    salient_pressure_prompt,
)


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


class TestSalientPressurePrompt:
    """The directive that pushes at least one generated choice to answer the
    dominant pressure. Each branch is the contract the choice layer reads."""

    @pytest.mark.parametrize("field,word", [
        ("suspicion", "suspicion"),
        ("wounds", "wounds"),
        ("debt", "debt"),
        ("scarcity", "scarcity"),
        ("faction_heat", "faction heat"),
        ("omen", "omen"),
    ])
    def test_each_pressure_above_threshold_names_its_answer(self, field, word):
        state = ThreadState(pressures=PressureState(**{field: 1.6}))
        assert salient_pressure_prompt(state).startswith(f"Answer {word}")

    def test_suspicion_takes_priority_over_a_co_active_pressure(self):
        # Branch order is the priority: suspicion is checked before wounds.
        state = ThreadState(pressures=PressureState(suspicion=2.0, wounds=2.0))
        assert salient_pressure_prompt(state).startswith("Answer suspicion")

    def test_falls_through_to_active_oath_cost(self):
        # No pressure dominates, but a priced oath is owed an accounting.
        state = ThreadState(
            pressures=PressureState(),
            soul_ledger=SoulLedger(active_oaths=[
                Oath(oath_id="o1", text="...", turn_sworn=1,
                     terms=OathTerms(subject="Hero", promised_action="serve", price="honor")),
            ]),
        )
        prompt = salient_pressure_prompt(state)
        assert "oath cost" in prompt and "honor" in prompt

    def test_quiet_state_with_no_priced_oath_is_empty(self):
        assert salient_pressure_prompt(ThreadState(pressures=PressureState())) == ""
