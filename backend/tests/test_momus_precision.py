"""Momus precision tests — fewer false positives, same protection.

The old validator flagged any title-case NPC near any scene-action verb.
These tests pin the refined contract:
  * Memories of the dead are grief, not hallucinations.
  * The dead may not act — strong or weak evidence flags them.
  * Absent-but-alive NPCs are flagged only on STRONG participation
    (speech, touch, entrance), never on weak verbs like "watches".
"""

from __future__ import annotations

import pytest

from app.agents.momus import Momus
from app.core.world_seeds import get_world_seed
from app.schemas.state import ThreadState
from app.services.canon import bootstrap_canon


@pytest.fixture
def momus() -> Momus:
    return Momus()


@pytest.fixture
def state() -> ThreadState:
    s = ThreadState()
    s.session.current_environment = "Ashfall (mining camp, the Northern Reaches)."
    s.canon = bootstrap_canon(get_world_seed("stone"), "Hero", "boy")
    return s


def _names(state: ThreadState) -> tuple[str, str]:
    """Return (present_name, absent_name) with exactly one NPC in scene."""
    ids = list(state.canon.npcs.keys())
    present_id, absent_id = ids[0], ids[1]
    state.canon.current_scene.present_npc_ids = [present_id]
    return state.canon.npcs[present_id].name, state.canon.npcs[absent_id].name


class TestDeadNPCs:
    @pytest.mark.asyncio
    async def test_dead_npc_speaking_is_flagged(self, momus, state):
        present, absent = _names(state)
        state.canon.npcs[f"npc_{absent.lower()}"].status = "dead"
        result = await momus.validate_prose(
            f'{absent} said, "Bring the lamp closer."', state
        )
        assert any("dead" in h for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_dead_npc_watching_is_flagged(self, momus, state):
        present, absent = _names(state)
        state.canon.npcs[f"npc_{absent.lower()}"].status = "dead"
        result = await momus.validate_prose(
            f"{absent} watches you from the doorway.", state
        )
        assert any("dead" in h for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_memory_of_dead_npc_is_not_flagged(self, momus, state):
        present, absent = _names(state)
        state.canon.npcs[f"npc_{absent.lower()}"].status = "dead"
        result = await momus.validate_prose(
            f"You remember how {absent} grabbed your wrist, years ago.", state
        )
        assert not result.hallucinations

    @pytest.mark.asyncio
    async def test_dream_of_dead_npc_is_not_flagged(self, momus, state):
        present, absent = _names(state)
        state.canon.npcs[f"npc_{absent.lower()}"].status = "dead"
        result = await momus.validate_prose(
            f"In your dream {absent} called your name again.", state
        )
        assert not result.hallucinations


class TestAbsentNPCs:
    @pytest.mark.asyncio
    async def test_absent_npc_speaking_is_flagged(self, momus, state):
        present, absent = _names(state)
        result = await momus.validate_prose(
            f'{absent} said, "You should not be here."', state
        )
        assert any("not present" in h for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_absent_npc_watching_from_distance_is_allowed(self, momus, state):
        present, absent = _names(state)
        result = await momus.validate_prose(
            f"Far down the row, {absent} watches the carts go by.", state
        )
        assert not result.hallucinations

    @pytest.mark.asyncio
    async def test_absent_npc_merely_mentioned_is_allowed(self, momus, state):
        present, absent = _names(state)
        result = await momus.validate_prose(
            f"{present} grumbles about {absent} and the unpaid wages.", state
        )
        assert not result.hallucinations

    @pytest.mark.asyncio
    async def test_present_npc_acting_is_allowed(self, momus, state):
        present, _ = _names(state)
        result = await momus.validate_prose(
            f'{present} said, "Hand me the chisel."', state
        )
        assert not result.hallucinations
