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

    def test_long_name_book_id_truncates_without_a_trailing_dash(self):
        # A long multi-word name whose slug + suffix exceeds 80 chars used to
        # truncate ONTO a separator, leaving a trailing "-" that
        # load_book_markdown's guard (slugify strips it) then rejected — the
        # bound book listed on the shelf but 404'd on open. The id must round-trip.
        state = _state()
        state.session.player_name = " ".join(["aa"] * 26)  # forces the 80-char boundary
        manifest = bind_book(
            state, [_chapter()], epitaph="Here lies a long-named soul.", death_reason="x"
        )
        assert not manifest.book_id.endswith("-")
        assert len(manifest.book_id) <= 80
        write_book(manifest)
        assert manifest.book_id in [b.book_id for b in list_books()]
        assert load_book_markdown(manifest.book_id) is not None  # opens, not a 404

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


class TestNameLengthCap:
    """InitRequest.name is capped to match the death-time sinks. Without it a
    name >80 chars passed /init but raised ValidationError when BookManifest /
    PlayVerdict were built at death (caught + logged), so the life was silently
    never recorded. Reject over-long names fast at the request boundary instead.
    """

    def test_over_cap_name_is_rejected(self):
        from app.schemas.state import InitRequest

        with pytest.raises(ValidationError):
            InitRequest(hamartia="Wrath", name="a" * 81)

    def test_at_cap_name_is_accepted(self):
        from app.schemas.state import InitRequest

        req = InitRequest(hamartia="Wrath", name="a" * 80)
        assert len(req.name) == 80

    def test_omitted_name_uses_the_default(self):
        from app.schemas.state import InitRequest

        assert InitRequest(hamartia="Wrath").name == "Stranger"

    def test_cap_matches_the_death_time_sinks(self):
        # If these drift, an over-long name could again pass /init and then be
        # silently dropped when the book/verdict are bound at death.
        import annotated_types as at

        from app.schemas.assay import PlayVerdict
        from app.schemas.book import BookManifest
        from app.schemas.state import InitRequest

        def _max_len(model, field):
            return next(
                (m.max_length for m in model.model_fields[field].metadata
                 if isinstance(m, at.MaxLen)),
                None,
            )

        init_cap = _max_len(InitRequest, "name")
        assert init_cap == 80
        assert _max_len(BookManifest, "player_name") == init_cap
        assert _max_len(PlayVerdict, "player_name") == init_cap
