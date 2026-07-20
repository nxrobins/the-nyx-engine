"""The Bookbinder — death's last service: the life becomes an artifact.

Assembles the Scribe's chapters into a BookManifest, renders the
markdown, and publishes both atomically into the books/ artifact
directory (the Morpheus conventions: module-relative default, UTF-8
only, temp-write + os.replace, fail-loud-per-file loading).

The library functions are what the title screen reads: the Tapestry,
as an actual shelf.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.book import BookManifest, Chapter
from app.schemas.cartridge import slugify
from app.schemas.state import ThreadState

logger = logging.getLogger("nyx.books")

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "books"
_MANIFEST_GLOB = "*.book.json"
_MAX_FILES = 512


def books_dir() -> Path:
    return Path(settings.books_dir) if settings.books_dir else _DEFAULT_DIR


def _book_id(state: ThreadState) -> str:
    name = slugify(state.session.player_name).replace("_", "-")
    pid = slugify(state.session.player_id).replace("_", "-")
    raw = f"{name}-{pid}-r{state.session.run_number}"
    # Strip AFTER truncating: slicing to 80 can land on a separator and
    # re-introduce a trailing "-", which load_book_markdown's guard
    # (slugify strips it) would then reject — a bound book that lists but 404s.
    return raw[:80].strip("-")


def book_id_for(state: ThreadState) -> str:
    """The deterministic book id for a thread.

    Public because a resumed death must be able to ask "did my book ever bind?"
    without a shelf scan: the id is a pure function of the thread, so the answer
    is `load_book_markdown(book_id_for(state)) is not None`.
    """
    return _book_id(state)


def _title(state: ThreadState) -> str:
    name = state.session.player_name
    hamartia = state.soul_ledger.hamartia
    if hamartia and hamartia != "Unformed":
        flaw_word = hamartia.split()[0].rstrip(",")
        return f"The {flaw_word} of {name}"
    return f"The Thread of {name}"


def bind_book(
    state: ThreadState,
    chapters: list[Chapter],
    *,
    epitaph: str,
    death_reason: str,
) -> BookManifest:
    """Assemble the manifest. Raises ValidationError if the life produced
    nothing bindable (no chapters) — the caller treats that as 'no book'."""
    vectors = state.soul_ledger.vectors
    settlement = ""
    if state.canon and state.canon.locations:
        first = next(iter(state.canon.locations.values()))
        settlement = first.region if first.kind in ("settlement",) else first.name
        # Prefer the settlement-tagged location when present.
        for loc in state.canon.locations.values():
            if "settlement" in loc.tags:
                settlement = loc.name
                break

    return BookManifest(
        book_version=1,
        book_id=_book_id(state),
        thread_stamp=f"{state.session.player_id}:{state.session.run_number}",
        player_name=state.session.player_name,
        title=_title(state),
        hamartia=state.soul_ledger.hamartia,
        life_voice=state.life_voice,
        settlement=settlement,
        epitaph=epitaph,
        death_reason=death_reason,
        died_turn=state.session.turn_count,
        soul_summary=(
            f"metis {vectors.metis:.1f} | bia {vectors.bia:.1f} | "
            f"kleos {vectors.kleos:.1f} | aidos {vectors.aidos:.1f}"
        ),
        chapters=sorted(chapters, key=lambda c: c.epoch_index),
    )


def render_markdown(manifest: BookManifest) -> str:
    lines = [
        f"# {manifest.title}",
        "",
        f"*Being the true account of {manifest.player_name}"
        + (f" of {manifest.settlement}" if manifest.settlement else "")
        + f", who carried the flaw of {manifest.hamartia or 'no name'} "
        f"and whose thread was cut at turn {manifest.died_turn}.*",
        "",
        f"> {manifest.epitaph}",
        "",
        "---",
        "",
    ]
    for chapter in manifest.chapters:
        lines += [f"## {chapter.title}", "", chapter.prose, "", "---", ""]
    lines += [
        f"*Soul at the severing: {manifest.soul_summary}*",
        "",
        f"*Written in this voice: {manifest.life_voice}*" if manifest.life_voice else "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_book(manifest: BookManifest) -> Path:
    """Publish manifest + markdown atomically. Returns the markdown path."""
    directory = books_dir()
    json_path = directory / f"{manifest.book_id}.book.json"
    md_path = directory / f"{manifest.book_id}.book.md"
    _atomic_write(json_path, manifest.model_dump_json(indent=2) + "\n")
    _atomic_write(md_path, render_markdown(manifest))
    logger.info(f"Book bound: {manifest.book_id} ({len(manifest.chapters)} chapter(s))")
    return md_path


def list_books() -> list[BookManifest]:
    """The library shelf. Fail-loud-per-file: one bad book never hides the rest."""
    directory = books_dir()
    if not directory.is_dir():
        return []
    manifests: list[BookManifest] = []
    for path in sorted(directory.glob(_MANIFEST_GLOB))[:_MAX_FILES]:
        try:
            manifests.append(
                BookManifest.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (ValidationError, UnicodeDecodeError, OSError) as exc:
            logger.warning(f"{path.name}: unreadable book ({exc!r}), skipped")
    return manifests


def load_book_markdown(book_id: str) -> str | None:
    """Fetch one bound life. The id is validated against the slug alphabet
    before touching the filesystem — no path traversal by book title."""
    if slugify(book_id).replace("_", "-") != book_id:
        return None
    path = books_dir() / f"{book_id}.book.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
