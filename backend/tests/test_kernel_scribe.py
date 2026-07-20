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


async def _none():
    """An awaitable that yields no chapter (the biographer came back empty)."""
    return None


async def _init(kernel: NyxKernel, hamartia: str = "Wrath of the Untempered") -> None:
    await kernel.initialize(
        hamartia=hamartia,
        player_id="scribe_test",
        name="Orin",
        gender="boy",
        first_memory="The weight of a heavy stone in my hand.",  # Ashfall
    )
    # THE PULSE calibration: birth is turn 0 — the breath is every life's
    # first action, restoring this file's original turn frame (init -> turn 1).
    await kernel.process_turn("Draw your first breath.")


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
        assert result.epitaph  # the Death Rite needs the carved line
        # The Rite does NOT wait on the biographer: a chapter draft measures ~40s.
        assert result.book_id == ""
        await kernel._bind_task          # the Bookbinder, behind the Rite
        assert kernel.state.book_id == "orin-scribe-test-r1"

        shelf = list_books()
        assert len(shelf) == 1
        book = shelf[0]
        assert book.title == "The Wrath of Orin"
        assert book.died_turn == 7
        # Two lived epochs + the Severing.
        assert [c.epoch_index for c in book.chapters] == [1, 2, 3]
        assert book.chapters[-1].covers_turns == (7, 7)
        assert "The Severing" in book.chapters[-1].title

        md = load_book_markdown(kernel.state.book_id)
        assert "**" not in md.splitlines()[0]  # title line is a clean heading
        assert "The Wrath of Orin" in md
        assert kernel._chapters == []  # manuscript handed to the binder

    @pytest.mark.asyncio
    async def test_death_before_any_boundary_still_binds(self, kernel):
        await _init(kernel)
        result = await kernel.process_turn("embrace the void")  # turn 2: death
        assert result.terminal
        await kernel._bind_task
        assert kernel.state.book_id
        book = list_books()[0]
        assert len(book.chapters) == 1
        assert book.chapters[0].covers_turns == (1, 2)
        assert "Severing" in book.chapters[0].title

    @pytest.mark.asyncio
    async def test_death_persists_epitaph_and_book_to_state(self, kernel):
        # V2-H2 (write half): the carved line is stamped onto ThreadState BEFORE
        # the terminal snapshot, so a resume re-shows the Death Rite whole. The
        # book link arrives later — the Bookbinder runs behind the Rite.
        await _init(kernel)
        result = await kernel.process_turn("embrace the void")  # turn 2: death
        assert result.terminal
        assert kernel.state.epitaph == result.epitaph and kernel.state.epitaph
        await kernel._bind_task
        assert kernel.state.book_id  # linked on the live thread once bound

    @pytest.mark.asyncio
    async def test_resumed_death_relinks_a_book_bound_behind_the_rite(self, kernel):
        """The terminal snapshot is written BEFORE the book binds (and the
        store's monotonic guard rightly refuses a same-turn rewrite), so a
        resumed death must resolve its book from the shelf — the durable record.
        The id is deterministic from the thread, so no scan is needed."""
        from app.services.durability import serialize_snapshot, SNAPSHOT_SCHEMA_VERSION

        await _init(kernel)
        await kernel.process_turn("embrace the void")
        await kernel._bind_task
        bound_id = kernel.state.book_id
        assert bound_id  # the life did bind a book

        # Snapshot the death AS IT WAS WRITTEN: before the binder finished.
        pre_bind = kernel.state.model_copy(deep=True)
        pre_bind.book_id = ""
        state_json, chapters_json = serialize_snapshot(pre_bind, [])
        snap = {
            "token": "tok", "player_id": "p", "thread_id": 1,
            "turn_count": pre_bind.session.turn_count,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "state_json": state_json, "chapters_json": chapters_json,
        }
        revived = NyxKernel.rehydrate(snap, "tok")
        assert revived.state.terminal is True
        assert revived.state.book_id == bound_id      # relinked from the shelf

    @pytest.mark.asyncio
    async def test_resumed_death_stays_unlinked_when_no_book_bound(self, kernel):
        # Honest: relink only reports a book that ACTUALLY exists on the shelf.
        from app.services.durability import serialize_snapshot, SNAPSHOT_SCHEMA_VERSION

        await _init(kernel)
        kernel.scribe.draft_chapter = lambda snapshot: _none()
        await kernel.process_turn("embrace the void")
        await kernel._bind_task

        unbound = kernel.state.model_copy(deep=True)
        unbound.book_id = ""
        state_json, chapters_json = serialize_snapshot(unbound, [])
        snap = {
            "token": "tok", "player_id": "p", "thread_id": 1,
            "turn_count": unbound.session.turn_count,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "state_json": state_json, "chapters_json": chapters_json,
        }
        revived = NyxKernel.rehydrate(snap, "tok")
        assert revived.state.terminal is True
        assert revived.state.book_id == ""     # unbound, not invented

    @pytest.mark.asyncio
    async def test_the_rite_does_not_wait_on_the_biographer(self, kernel):
        """The whole point: a chapter draft measures ~40s against a 15s
        interactive budget. The death must commit and present immediately, with
        the book binding behind it."""
        await _init(kernel)
        slow_started = asyncio.Event()

        async def slow_draft(snapshot):
            slow_started.set()
            await asyncio.sleep(0.4)          # stand-in for the ~40s draft
            return None                        # unbindable — the death still stands

        kernel.scribe.draft_chapter = slow_draft
        result = await kernel.process_turn("embrace the void")

        # The Rite is already here while the biographer is still working.
        assert result.terminal and result.epitaph
        assert kernel.state.terminal is True   # permanence committed
        assert not kernel._bind_task.done()    # ...and the book is still binding
        await kernel._bind_task
        assert slow_started.is_set()
        assert kernel.state.book_id == ""      # unbound, not undead

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
