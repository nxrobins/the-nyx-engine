"""Scribe P3 contracts — the Chapter and the Book.

The Scribe drafts each lived epoch as a chapter, write-behind, in a
life-voice discovered at the Fork. At death the chapters bind into a
Book — the artifact that turns the Tapestry into a library.

Same constitutional ground as every Morpheus organ: the Scribe revises
the TELLING, never the events. A chapter retells lived prose; it is
gated deterministically (scribe_gate) and carries validity stamps. A
chapter that fails simply doesn't exist — the book has fewer chapters,
the game never notices.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BOOK_VERSION: int = 1

MAX_CHAPTER_CHARS = 8000
MAX_CHAPTERS = 24


class Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epoch_index: int = Field(ge=1, le=MAX_CHAPTERS)
    title: str = Field(min_length=3, max_length=120)
    covers_turns: tuple[int, int]            # inclusive lived range
    prose: str = Field(min_length=100, max_length=MAX_CHAPTER_CHARS)
    thread_stamp: str = Field(min_length=3, max_length=120)
    based_on_turn: int = Field(ge=1)         # snapshot turn it was drafted from

    @model_validator(mode="after")
    def _range_sane(self) -> Chapter:
        start, end = self.covers_turns
        if start < 1 or end < start:
            raise ValueError(f"covers_turns {self.covers_turns} is not a sane range")
        if self.based_on_turn < end:
            raise ValueError(
                "based_on_turn precedes the chapter's own events — "
                "the Scribe cannot draft what has not been lived"
            )
        return self


class BookManifest(BaseModel):
    """The bound life. Written once, at death, atomically."""
    model_config = ConfigDict(extra="forbid")

    book_version: Literal[1]
    book_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]{2,79}$")
    thread_stamp: str = Field(min_length=3, max_length=120)
    player_name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=3, max_length=160)
    hamartia: str = Field(default="", max_length=80)
    life_voice: str = Field(default="", max_length=600)
    settlement: str = Field(default="", max_length=80)
    epitaph: str = Field(min_length=3, max_length=600)
    death_reason: str = Field(default="", max_length=600)
    died_turn: int = Field(ge=1)
    soul_summary: str = Field(default="", max_length=300)
    chapters: list[Chapter] = Field(min_length=1, max_length=MAX_CHAPTERS)

    @model_validator(mode="after")
    def _chapters_ordered(self) -> BookManifest:
        indices = [c.epoch_index for c in self.chapters]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            raise ValueError(f"chapter epoch_index sequence invalid: {indices}")
        return self


class ScribeSnapshot(BaseModel):
    """Frozen input for one chapter draft — the photograph, never the room."""
    model_config = ConfigDict(extra="forbid")

    thread_stamp: str
    epoch_index: int = Field(ge=1, le=MAX_CHAPTERS)
    epoch_name: str = Field(min_length=1, max_length=60)
    covers_turns: tuple[int, int]
    boundary_turn: int                      # the turn this snapshot was taken at
    prose_window: list[str]                 # the lived epoch's prose, in order
    factual_chronicle: list[str]
    chronicle: list[str]
    life_voice: str = ""
    player_name: str
    player_age: int
    hamartia: str = ""
    settlement: str = ""
    npc_names: list[str] = Field(default_factory=list)  # known canon names, any status
    death_reason: str = ""                  # set only for the final chapter
    epitaph: str = ""                       # set only for the final chapter
