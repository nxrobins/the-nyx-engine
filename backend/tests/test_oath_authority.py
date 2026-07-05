"""A bogus Lachesis oath_violation cannot doom an oathless thread (audit H1).

The mock Lachesis never emits `oath_violation`, so the hermetic suite was blind
to this whole path — which is how the bug survived 1044 green tests. This injects
the field at the agent seam (exactly what a real fast model can do) and proves the
deterministic guard refuses it: an unverified model string, with no oath sworn,
does not seal an inescapable broken-oath doom.
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
async def test_bogus_oath_violation_does_not_doom_oathless_thread(kernel: NyxKernel):
    await _init(kernel)
    assert not kernel.state.soul_ledger.active_oaths  # the player swore nothing

    original = kernel.lachesis.evaluate

    async def _inject(state, action):
        resp = await original(state, action)
        resp.oath_violation = "none"  # the classic truthy model tic
        return resp

    kernel.lachesis.evaluate = _inject  # type: ignore[method-assign]

    result = await kernel.process_turn("I walk to the well and look inside.")

    # No broken-oath doom was sealed; the thread lives.
    assert kernel.state.doom.cause != "broken_oath"
    assert result.terminal is False
