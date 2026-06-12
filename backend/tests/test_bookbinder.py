"""Bookbinder tests — assembly, atomic publication, the library shelf."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.world_seeds import get_world_seed
from app.schemas.book import BookManifest, Chapter
from app.schemas.state import SessionData, ThreadState
from app.services.bookbinder import (
    bind_book,
    books_dir,
    list_books,
    load_book_markdown,
    render_markdown,
    write_book,
)
from app.services.canon import bootstrap_canon


def _chapter(index=1, covers=(1, 3)) -> Chapter:
    return Chapter(
        epoch_index=index,
        title=f"Chapter {index}: The Hearth",
        covers_turns=covers,
        prose=(
            "In Ashfall the winters were counted in candle stubs, and Orin "
            "learned early that Maren's silences carried more weight than "
            "Kael's fists ever could have."
        ),
        thread_stamp="p:1",
        based_on_turn=covers[1],
    )


def _state() -> ThreadState:
    s = ThreadState(
        session=SessionData(player_id="p", player_name="Orin", turn_count=7, run_number=1),
    )
    s.soul_ledger.hamartia = "Wrath of the Untempered"
    s.life_voice = "Short, percussive sentences."
    s.canon = bootstrap_canon(get_world_seed("stone"), "Orin", "boy")
    return s


class TestBinding:
    def test_bind_and_render(self):
        manifest = bind_book(
            _state(), [_chapter()], epitaph="Here lies Orin.", death_reason="The shaft."
        )
        assert manifest.book_id == "orin-p-r1"
        assert manifest.title == "The Wrath of Orin"
        assert manifest.settlement == "Ashfall"
        md = render_markdown(manifest)
        assert md.startswith("# The Wrath of Orin")
        assert "> Here lies Orin." in md
        assert "## Chapter 1: The Hearth" in md

    def test_no_chapters_is_unbindable(self):
        with pytest.raises(ValidationError):
            bind_book(_state(), [], epitaph="Here lies Orin.", death_reason="x")

    def test_chapters_sorted_by_epoch(self):
        manifest = bind_book(
            _state(),
            [_chapter(2, (4, 6)), _chapter(1, (1, 3))],
            epitaph="Here lies Orin.",
            death_reason="x",
        )
        assert [c.epoch_index for c in manifest.chapters] == [1, 2]


class TestLibrary:
    def test_write_list_load_roundtrip(self):
        manifest = bind_book(
            _state(), [_chapter()], epitaph="Here lies Orin.", death_reason="The shaft."
        )
        write_book(manifest)
        shelf = list_books()
        assert [b.book_id for b in shelf] == ["orin-p-r1"]
        md = load_book_markdown("orin-p-r1")
        assert md is not None and "The Wrath of Orin" in md

    def test_bad_manifest_skipped_on_shelf(self):
        manifest = bind_book(
            _state(), [_chapter()], epitaph="Here lies Orin.", death_reason="x"
        )
        write_book(manifest)
        directory = books_dir()
        (directory / "broken.book.json").write_text("{ not json", encoding="utf-8")
        shelf = list_books()
        assert len(shelf) == 1  # the broken spine never hides the rest

    def test_missing_book_is_none(self):
        assert load_book_markdown("no-such-life") is None

    def test_path_traversal_guarded(self):
        assert load_book_markdown("../../etc/passwd") is None
        assert load_book_markdown("..\\secrets") is None

    def test_atomic_tmp_never_listed(self):
        directory = books_dir()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "partial.tmp").write_text("{", encoding="utf-8")
        assert list_books() == []
