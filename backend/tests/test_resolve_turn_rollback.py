"""A mid-turn exception must not leave the turn half-advanced (audit M6).

_resolve_turn increments the turn counter and sets epoch metadata before its
awaits. Before the fix, an exception anywhere after that left the counter
advanced with nothing committed — the next turn skipped a number and the age
jumped. Material state commits only in _finalize_turn, so the guard restores the
session snapshot on any exception and re-raises.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _init(k: NyxKernel) -> None:
    await k.initialize(
        hamartia="Unformed",
        player_id="test_player",
        name="Hero",
        gender="boy",
        first_memory="A light in the distance I could not reach.",
    )


@pytest.mark.asyncio
async def test_midturn_exception_rolls_back_the_turn_counter(kernel: NyxKernel):
    await _init(kernel)
    turn_before = kernel.state.session.turn_count
    age_before = kernel.state.session.player_age
    phase_before = kernel.state.session.epoch_phase

    async def _boom(*args, **kwargs):
        raise RuntimeError("a service blew up mid-turn")

    # Lachesis runs after the counter/metadata are advanced — a perfect place to
    # inject a mid-turn failure.
    kernel.lachesis.evaluate = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await kernel._resolve_turn("I walk to the market.")

    # The half-mutation is undone: the next turn won't skip a number or jump age.
    assert kernel.state.session.turn_count == turn_before
    assert kernel.state.session.player_age == age_before
    assert kernel.state.session.epoch_phase == phase_before


@pytest.mark.asyncio
async def test_successful_turn_still_advances(kernel: NyxKernel):
    await _init(kernel)
    turn_before = kernel.state.session.turn_count
    await kernel._resolve_turn("I look around the room.")
    assert kernel.state.session.turn_count == turn_before + 1
