"""Dreams are the transitions between chapters (THE PULSE sub-slice 4, P1-C10).

Nigel's ruling: a dream at every chapter boundary. Childhood behavior is
bit-identical (epoch RESOLUTIONs close chapters); adulthood gains a dream at
every crucible close; vignettes and terminal beats never dream.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.kernel import NyxKernel


def _ctx(*, terminal: bool = False, phase: int = 4, beat: str = "OPEN"):
    return SimpleNamespace(
        terminal=terminal, phase=phase, beat_position=beat,
        outcome=SimpleNamespace(state=None),
    )


@pytest.fixture
def kernel(monkeypatch) -> NyxKernel:
    k = NyxKernel()
    # weave_dream is never awaited in these predicate tests; return a coroutine
    # that closes immediately when the task is created/cancelled.
    async def _fake_dream(state):
        return "a river of ash"
    monkeypatch.setattr(k.hypnos, "weave_dream", _fake_dream)
    return k


def _fires(kernel, ctx) -> bool:
    task = kernel._maybe_start_dream_task(ctx)
    if task is None:
        return False
    task.cancel()
    return True


@pytest.mark.asyncio
async def test_childhood_resolution_still_dreams(kernel):
    assert _fires(kernel, _ctx(phase=3, beat="RESOLUTION")) is True


@pytest.mark.asyncio
async def test_childhood_setup_and_complication_do_not(kernel):
    assert _fires(kernel, _ctx(phase=2, beat="SETUP")) is False
    assert _fires(kernel, _ctx(phase=2, beat="COMPLICATION")) is False


@pytest.mark.asyncio
async def test_adult_crucible_dreams_at_every_chapter_close(kernel):
    # The generalization: adulthood dreamed NEVER before; now every crucible
    # (any adult full-pipeline beat) closes a chapter and dreams.
    for beat in ("SETUP", "COMPLICATION", "RESOLUTION", "OPEN"):
        assert _fires(kernel, _ctx(phase=4, beat=beat)) is True


@pytest.mark.asyncio
async def test_terminal_never_dreams(kernel):
    assert _fires(kernel, _ctx(terminal=True, phase=4)) is False
    assert _fires(kernel, _ctx(terminal=True, phase=3, beat="RESOLUTION")) is False
