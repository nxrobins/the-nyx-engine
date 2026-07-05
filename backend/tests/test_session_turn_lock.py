"""Concurrent turns on one session are serialized (audit H2).

Without a per-session lock, two turns in flight at once (double-click, /action +
/turn, two tabs) both deepcopy a pre-commit state and run full pipelines; the
second's `self.state = outcome.state` commit discards the first turn's oaths /
doom / canon while its DB row remains — state and DB diverge permanently.

These prove the lock by instrumenting mid-turn concurrency: a gauge that reads 2
without the lock reads 1 with it.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.kernel import NyxKernel


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _init(k: NyxKernel) -> None:
    await k.initialize(
        hamartia="Unformed", player_id="p", name="Hero", gender="boy",
        first_memory="A light in the distance I could not reach.",
    )


def _install_concurrency_gauge(kernel: NyxKernel) -> dict:
    """Instrument Lachesis (which runs mid-turn, inside the lock) to record the
    peak number of turns executing simultaneously."""
    gauge = {"cur": 0, "max": 0}
    original = kernel.lachesis.evaluate

    async def _instrumented(state, action):
        gauge["cur"] += 1
        gauge["max"] = max(gauge["max"], gauge["cur"])
        await asyncio.sleep(0.02)  # a real yield point where interleaving would show
        try:
            return await original(state, action)
        finally:
            gauge["cur"] -= 1

    kernel.lachesis.evaluate = _instrumented  # type: ignore[method-assign]
    return gauge


@pytest.mark.asyncio
async def test_concurrent_sync_turns_are_serialized(kernel: NyxKernel):
    await _init(kernel)
    gauge = _install_concurrency_gauge(kernel)
    before = kernel.state.session.turn_count

    await asyncio.gather(kernel.process_turn("action A"), kernel.process_turn("action B"))

    assert gauge["max"] == 1                                   # never overlapped
    assert kernel.state.session.turn_count == before + 2       # both turns ran


@pytest.mark.asyncio
async def test_concurrent_streaming_turns_are_serialized(kernel: NyxKernel):
    await _init(kernel)
    gauge = _install_concurrency_gauge(kernel)

    async def _drain(action: str):
        return [chunk async for chunk in kernel.process_turn_stream(action)]

    await asyncio.gather(_drain("action A"), _drain("action B"))

    assert gauge["max"] == 1
