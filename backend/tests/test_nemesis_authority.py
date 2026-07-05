"""A model-claimed lethal_punishment cannot fabricate an oath break (audit H5).

The concrete scenario the audit named: Nemesis is invoked for a mere prophecy-level
trigger, but the LLM answers with "intervention_type": "lethal_punishment". Before
the fix that tier survived, and the resolver then applied oath-broken consequences
with no oath broken. The tier is the kernel's (force_type), not the model's.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.nemesis import Nemesis
from app.core.config import settings
from app.schemas.state import ThreadState


@pytest.mark.asyncio
async def test_model_lethal_claim_is_capped_to_authorized_prophecy():
    raw = (
        '{"intervene": true, "intervention_type": "lethal_punishment", '
        '"updated_prophecy": "ruin comes", "punishment_description": "the lash"}'
    )
    nem = Nemesis()
    with patch.object(settings, "nemesis_model", "openai/mercury-2"), \
         patch("app.agents.nemesis.llm.generate", new=AsyncMock(return_value=raw)):
        result = await nem._generate(
            ThreadState(), "I boast in the square.", None, force_type="prophecy_update"
        )
    assert result.intervention_type == "prophecy_update"


@pytest.mark.asyncio
async def test_real_oath_break_stays_lethal_even_if_model_downplays():
    raw = (
        '{"intervene": true, "intervention_type": "prophecy_update", '
        '"updated_prophecy": "a whisper", "punishment_description": ""}'
    )
    nem = Nemesis()
    with patch.object(settings, "nemesis_model", "openai/mercury-2"), \
         patch("app.agents.nemesis.llm.generate", new=AsyncMock(return_value=raw)):
        result = await nem._generate(
            ThreadState(), "I break my sworn word.", "oath_1", force_type="lethal_punishment"
        )
    assert result.intervention_type == "lethal_punishment"
