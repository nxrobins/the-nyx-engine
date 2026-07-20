"""Kernel ↔ Assayer integration — death weighs the life; the book echoes forward."""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.services.assayer import list_verdicts


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


@pytest.fixture(autouse=True)
def _no_eris(monkeypatch):
    import app.agents.eris as eris_module
    monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)


async def _init(kernel: NyxKernel, player_id: str = "assay_test") -> None:
    await kernel.initialize(
        hamartia="Wrath of the Untempered",
        player_id=player_id,
        name="Orin",
        gender="boy",
        first_memory="The weight of a heavy stone in my hand.",
    )
    # THE PULSE calibration: birth is turn 0 — the breath is every life's
    # first action, restoring this file's original turn frame (init -> turn 1).
    await kernel.process_turn("Draw your first breath.")


class TestDeathWritesVerdict:
    @pytest.mark.asyncio
    async def test_world_id_tracked_from_birth(self, kernel):
        await _init(kernel)
        assert kernel.state.world_id  # the stone cartridge id (ashfall) — supersedes the builtin

    @pytest.mark.asyncio
    async def test_verdict_written_at_death(self, kernel):
        await _init(kernel)
        await kernel.process_turn("hide behind the carts")
        result = await kernel.process_turn("embrace the void")
        assert result.terminal
        # The weighing rides with the Bookbinder BEHIND the Rite, so it carries
        # the real book link instead of an empty one.
        await kernel._bind_task

        shelf = list_verdicts()
        assert len(shelf) == 1
        v = shelf[0]
        assert v.world_id == kernel.state.world_id
        assert v.thread_stamp == "assay_test:1"
        assert v.died_turn == 3
        assert v.book_id == kernel.state.book_id
        assert v.death_cause  # "You chose oblivion..."

    @pytest.mark.asyncio
    async def test_assay_failure_never_blocks_death(self, kernel, monkeypatch):
        await _init(kernel)

        import app.core.kernel as kernel_module

        def broken(*args, **kwargs):
            raise RuntimeError("the scales shattered")

        monkeypatch.setattr(kernel_module, "compute_verdict", broken)
        result = await kernel.process_turn("embrace the void")
        assert result.terminal          # the death stands
        await kernel._bind_task         # the weighing fails behind the Rite
        assert list_verdicts() == []    # unweighed, not undead


class TestAncestorBookFlourish:
    @pytest.mark.asyncio
    async def test_second_run_inherits_the_book_diegetically(self, kernel, monkeypatch):
        # Life one: die, get bound.
        await _init(kernel)
        first = await kernel.process_turn("embrace the void")
        await kernel._bind_task          # the book binds behind the Rite
        assert kernel.state.book_id
        first_title = "The Wrath of Orin"

        # Life two: the hermetic suite has no DB, so run_number would pin
        # to 1 — simulate one prior dead thread so run_number computes 2.
        import app.core.kernel as kernel_module

        async def one_ancestor(player_id):
            return [{"thread_id": 1}]

        monkeypatch.setattr(kernel_module, "get_dead_threads", one_ancestor)

        reborn = NyxKernel()
        await _init(reborn)
        assert reborn.state.session.run_number == 2
        assert first_title in reborn.state.world_context
        assert "repeat its lines wrongly" in reborn.state.world_context

    @pytest.mark.asyncio
    async def test_first_run_has_no_book_echo(self, kernel):
        await _init(kernel)
        assert "A book circulates" not in kernel.state.world_context
