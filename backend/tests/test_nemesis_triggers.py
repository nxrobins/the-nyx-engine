"""Nemesis trigger tests — abuse earns the lash, imbalance earns prophecy.

Pins the v3.0 contract: a committed character (high imbalance, clean
hands) gets prophecy updates, never punishment. Punishment requires
abuse signals, or extreme imbalance compounded WITH a moderate one.
"""

from __future__ import annotations

import pytest

from app.agents.nemesis import Nemesis
from app.core.config import settings
from app.schemas.state import SoulVectors, ThreadState


@pytest.fixture
def nemesis() -> Nemesis:
    return Nemesis()


def _committed_state() -> ThreadState:
    """A devoted schemer: extreme imbalance, no abuse signals."""
    state = ThreadState()
    state.soul_ledger.vectors = SoulVectors(metis=9.5, bia=1.0, kleos=5.0, aidos=5.0)
    return state


class TestImbalanceAlone:
    @pytest.mark.asyncio
    async def test_committed_character_gets_prophecy_not_punishment(self, nemesis):
        state = _committed_state()
        result = await nemesis.evaluate(state, "study the lock mechanism")
        assert result.intervene
        assert result.intervention_type == "prophecy_update"

    @pytest.mark.asyncio
    async def test_balanced_clean_soul_is_left_alone(self, nemesis):
        state = ThreadState()  # all vectors 5.0, no pressures
        result = await nemesis.evaluate(state, "walk to the well")
        assert not result.intervene


class TestAbuseSignals:
    @pytest.mark.asyncio
    async def test_exploit_pattern_earns_punishment(self, nemesis):
        state = ThreadState()
        state.pressures.exploit_score = 2.0
        result = await nemesis.evaluate(state, "repeat the trick again")
        assert result.intervene
        assert result.intervention_type == "punishment"

    @pytest.mark.asyncio
    async def test_runaway_suspicion_earns_punishment(self, nemesis):
        state = ThreadState()
        state.pressures.suspicion = 3.0
        result = await nemesis.evaluate(state, "slip through the crowd")
        assert result.intervention_type == "punishment"

    @pytest.mark.asyncio
    async def test_imbalance_compounded_with_moderate_abuse_punishes(self, nemesis):
        state = _committed_state()
        state.pressures.exploit_score = 1.2  # below the solo threshold of 2.0
        result = await nemesis.evaluate(state, "run the same con once more")
        assert result.intervention_type == "punishment"

    @pytest.mark.asyncio
    async def test_moderate_abuse_alone_below_thresholds_no_punishment(self, nemesis):
        state = ThreadState()  # balanced soul
        state.pressures.exploit_score = 1.2
        result = await nemesis.evaluate(state, "try the trick")
        assert result.intervention_type != "punishment"


class TestOathBreak:
    @pytest.mark.asyncio
    async def test_broken_oath_is_always_lethal_type(self, nemesis):
        state = ThreadState()
        result = await nemesis.evaluate(state, "abandon them", oath_broken="oath_x")
        assert result.intervene
        assert result.intervention_type == "lethal_punishment"


class TestProphecyThreshold:
    @pytest.mark.asyncio
    async def test_threshold_imbalance_sharpens_prophecy(self, nemesis):
        state = ThreadState()
        # Imbalance exactly at the threshold (10 - 4 = 6)
        state.soul_ledger.vectors = SoulVectors(
            metis=10.0, bia=4.0, kleos=5.0, aidos=5.0,
        )
        assert settings.nemesis_imbalance_threshold == 6.0
        result = await nemesis.evaluate(state, "press on")
        assert result.intervene
        assert result.intervention_type == "prophecy_update"
        assert result.updated_prophecy
