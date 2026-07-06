"""The life opens AT BIRTH (THE PULSE calibration — Nigel's playtest ruling).

Turn 0 is the coming-into-the-world: age 0, a single authored continuation
choice, the airy vignette register. The first breath lands on turn 1 (the
HEARTH, age 3) — the first chapter boundary IS the time skip. Ages then hold
constant within each childhood epoch, jumping only between chapters.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _born(k: NyxKernel):
    return await k.initialize(
        hamartia="Unformed", player_id="p", name="Hero", gender="boy",
        first_memory="The weight of a heavy stone in my hand.",
    )


@pytest.mark.asyncio
async def test_birth_is_turn_zero_age_zero(kernel):
    result = await _born(kernel)
    s = kernel.state.session
    assert result.turn_number == 0
    assert s.turn_count == 0
    assert s.player_age == 0
    assert s.beat_position == "BIRTH"
    assert s.beat_kind == "vignette"          # the airy register
    assert s.ui_mode == "buttons"


@pytest.mark.asyncio
async def test_birth_offers_exactly_the_breath(kernel):
    result = await _born(kernel)
    assert result.ui_choices == ["Draw your first breath."]


@pytest.mark.asyncio
async def test_first_breath_lands_on_the_hearth(kernel):
    await _born(kernel)
    result = await kernel.process_turn("Draw your first breath.")
    s = kernel.state.session
    assert result.turn_number == 1
    assert s.turn_count == 1
    assert s.player_age == 3                  # the first chapter boundary skips years
    assert s.epoch_phase == 1
    assert result.prose != ""


@pytest.mark.asyncio
async def test_age_never_moves_within_a_childhood_chapter(kernel):
    await _born(kernel)
    ages = []
    for _ in range(9):
        await kernel.process_turn("look around")
        ages.append(kernel.state.session.player_age)
    # Three chapters, three ages, constant within each (3,3,3 / 7,7,7 / 12,12,12).
    assert ages == [3, 3, 3, 7, 7, 7, 12, 12, 12]
