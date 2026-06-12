"""Kernel ↔ Scribe integration — live, die, get bound.

Death paths use the self-destruct keyword ("embrace the void") so the
terminal turn is deterministic — no Eris pinning needed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.kernel import NyxKernel
from app.services.bookbinder import list_books, load_book_markdown


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _init(kernel: NyxKernel, hamartia: str = "Wrath of the Untempered") -> None:
    await kernel.initialize(
        hamartia=hamartia,
        player_id="scribe_test",
        name="Orin",
        gender="boy",
        first_memory="The weight of a heavy stone in my hand.",  # Ashfall
    )


class TestLifeVoice:
    @pytest.mark.asyncio
    async def test_chosen_hamartia_discovers_voice_at_birth(self, kernel):
        await _init(kernel)
        assert "percussive" in kernel.state.life_voice

    @pytest.mark.asyncio
    async def test_unformed_discovers_voice_at_the_fork(self, kernel):
        await _init(kernel, hamartia="Unformed")
        assert kernel.state.life_voice == ""
        for i in range(9):  # turns 2..10 — the Fork fires at 10
            await kernel.process_turn(f"hide and wait {i}")
        assert kernel.state.soul_ledger.hamartia != "Unformed"
        assert kernel.state.life_voice != ""


class TestWriteBehind:
    @pytest.mark.asyncio
    async def test_chapters_shelve_at_boundaries(self, kernel):
        await _init(kernel)
        await kernel.process_turn("hide behind the carts")
        await kernel.process_turn("hide the stone")          # turn 3: fires ch.1
        await asyncio.sleep(0)
        await kernel.process_turn("work the pile")           # turn 4: harvest
        assert [c.epoch_index for c in kernel._chapters] == [1]
        assert kernel._chapters[0].covers_turns == (1, 3)

    @pytest.mark.asyncio
    async def test_reset_clears_the_manuscript(self, kernel):
        await _init(kernel)
        await kernel.process_turn("hide behind the carts")
        await kernel.process_turn("hide the stone")
        await asyncio.sleep(0)
        await kernel.process_turn("work the pile")
        assert kernel._chapters
        kernel.reset()
        assert kernel._chapters == []
        assert kernel._scribe_task is None


class TestDeathBindsTheBook:
    @pytest.fixture(autouse=True)
    def _no_eris(self, monkeypatch):
        # Pin chaos off: an Eris miracle can legitimately cheat even a
        # self-chosen death, which would make the death turn flaky.
        import app.agents.eris as eris_module
        monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)

    @pytest.mark.asyncio
    async def test_full_life_becomes_a_book(self, kernel):
        await _init(kernel)
        for action in ["hide behind the carts", "hide the stone",
                       "work the pile", "ask Kael", "say nothing"]:
            await kernel.process_turn(action)                # turns 2..6
        await asyncio.sleep(0)
        result = await kernel.process_turn("embrace the void")  # turn 7: death
        assert result.terminal
        assert result.book_id == "orin-scribe-test-r1"

        shelf = list_books()
        assert len(shelf) == 1
        book = shelf[0]
        assert book.title == "The Wrath of Orin"
        assert book.died_turn == 7
        # Two lived epochs + the Severing.
        assert [c.epoch_index for c in book.chapters] == [1, 2, 3]
        assert book.chapters[-1].covers_turns == (7, 7)
        assert "The Severing" in book.chapters[-1].title

        md = load_book_markdown(result.book_id)
        assert "**" not in md.splitlines()[0]  # title line is a clean heading
        assert "The Wrath of Orin" in md
        assert kernel._chapters == []  # manuscript cleared after binding

    @pytest.mark.asyncio
    async def test_death_before_any_boundary_still_binds(self, kernel):
        await _init(kernel)
        result = await kernel.process_turn("embrace the void")  # turn 2: death
        assert result.terminal
        assert result.book_id
        book = list_books()[0]
        assert len(book.chapters) == 1
        assert book.chapters[0].covers_turns == (1, 2)
        assert "Severing" in book.chapters[0].title

    @pytest.mark.asyncio
    async def test_binding_failure_never_blocks_death(self, kernel, monkeypatch):
        await _init(kernel)

        async def broken(snapshot):
            raise RuntimeError("the ink ran dry")

        monkeypatch.setattr(kernel.scribe, "draft_chapter", broken)
        result = await kernel.process_turn("embrace the void")
        assert result.terminal           # the death stands
        assert result.book_id == ""      # unbound, not undead
        assert list_books() == []
