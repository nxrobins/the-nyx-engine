"""Death permanence is enforced by the engine — the terminal latch (audit C1).

Before this, ThreadState carried no terminal marker and neither turn entrypoint
refused a dead thread: a keyword/dead-soul death with no active doom let the next
action resolve as a living turn, and a doom death re-ran the whole death path —
re-binding a second book and minting a duplicate assay verdict (polluting the
ouroboros signal). The only thing stopping it was the frontend unmounting inputs.

These tests pin the engine-level guarantee: once a death commits, the latch is
set and every further action — sync or streaming — is a no-op.
"""

from __future__ import annotations

import json

import pytest

from app.core.kernel import NyxKernel, TurnContext


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


async def _kill(k: NyxKernel, reason: str = "Soul collapsed under its own weight.") -> None:
    """Drive a committed death through the real terminal path."""
    ctx: TurnContext = await k._resolve_turn("look around")
    ctx.terminal = True
    ctx.death_reason = reason
    ctx.outcome.terminal = True
    ctx.outcome.death_reason = reason
    await k._handle_death(ctx)


class TestLatchIsSetOnDeath:
    @pytest.mark.asyncio
    async def test_handle_death_sets_the_latch(self, kernel: NyxKernel):
        await _init(kernel)
        assert kernel.state.terminal is False
        await _kill(kernel, "Eaten by wolves.")
        assert kernel.state.terminal is True
        assert kernel.state.death_reason == "Eaten by wolves."


class TestSyncTurnRefusesAfterDeath:
    @pytest.mark.asyncio
    async def test_dead_thread_refuses_action(self, kernel: NyxKernel):
        await _init(kernel)
        await _kill(kernel)
        turn_before = kernel.state.session.turn_count
        vectors_before = kernel.state.soul_ledger.vectors.model_dump()

        result = await kernel.process_turn("I stand up and walk to the market.")

        assert result.terminal is True
        assert "SEVERED" in result.prose
        # No turn advance, no soul mutation — the action never ran.
        assert kernel.state.session.turn_count == turn_before
        assert kernel.state.soul_ledger.vectors.model_dump() == vectors_before

    @pytest.mark.asyncio
    async def test_dead_thread_does_not_rebind_book_or_reverdict(self, kernel: NyxKernel):
        await _init(kernel)
        await _kill(kernel)

        calls = {"n": 0}
        original = kernel._bind_book_at_death

        async def _spy(*a, **kw):
            calls["n"] += 1
            return await original(*a, **kw)

        kernel._bind_book_at_death = _spy  # type: ignore[method-assign]
        await kernel.process_turn("try to cheat death")
        # The guard returns before _handle_death, so no second book/verdict.
        assert calls["n"] == 0


class TestStreamTurnRefusesAfterDeath:
    @pytest.mark.asyncio
    async def test_stream_refuses_and_does_not_advance(self, kernel: NyxKernel):
        await _init(kernel)
        await _kill(kernel)
        turn_before = kernel.state.session.turn_count

        frames = [f async for f in kernel.process_turn_stream("one more step")]
        payloads = [json.loads(f[len("data: "):]) for f in frames if f.startswith("data: ")]
        state_frames = [p for p in payloads if p.get("type") == "state"]

        assert state_frames, "a state frame must still be emitted"
        assert state_frames[-1]["terminal"] is True
        assert state_frames[-1]["ui_choices"] == []
        # No mechanic/deliberation frame — the council never convened.
        assert not any(p.get("type") == "mechanic" for p in payloads)
        assert kernel.state.session.turn_count == turn_before
