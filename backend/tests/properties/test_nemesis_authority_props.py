"""Commitment 1 (consequence is law) — Nemesis cannot self-escalate its tier (audit H5).

The intervention tier (prophecy_update < punishment < lethal_punishment) decides
downstream consequence: the resolver reads `lethal_punishment` as an oath break
and applies oath-broken pressure/relationship damage. That tier is the kernel's
decision, carried in `force_type` — lethal only when an oath actually broke. This
proves the model's returned `intervention_type`, whatever it claims, never exceeds
the authorized tier, and that a real lethal authorization is honored.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from hypothesis import given
from hypothesis import strategies as st

from app.agents.nemesis import Nemesis
from app.core.config import settings
from app.schemas.state import ThreadState

_TIERS = ["prophecy_update", "punishment", "lethal_punishment"]
_SEV = {t: i for i, t in enumerate(_TIERS)}


@given(
    claimed=st.sampled_from(_TIERS + ["apocalypse", "", "LETHAL_PUNISHMENT"]),
    force=st.sampled_from(_TIERS),
)
def test_model_tier_never_exceeds_authorization(claimed, force):
    raw = (
        '{"intervene": true, "intervention_type": "%s", '
        '"updated_prophecy": "the sky darkens", '
        '"punishment_description": "a reckoning"}' % claimed
    )
    nem = Nemesis()

    async def _run():
        with patch.object(settings, "nemesis_model", "openai/mercury-2"), \
             patch("app.agents.nemesis.llm.generate", new=AsyncMock(return_value=raw)):
            return await nem._generate(ThreadState(), "I do a thing.", None, force_type=force)

    result = asyncio.run(_run())
    # Whatever the model claimed, the effective tier never exceeds the authorized one.
    assert _SEV[result.intervention_type] <= _SEV[force]
    # And a genuine lethal authorization (an actual oath break) is honored.
    if force == "lethal_punishment":
        assert result.intervention_type == "lethal_punishment"
