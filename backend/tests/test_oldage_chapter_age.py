"""Old-age doom reads the CHAPTER age, not the turn count (audit V2-C2).

Under THE PULSE, adult age advances per CHAPTER close, not per turn — a life of
dense vignettes accrues many turns at a young age. The old-age doom must key on
session.player_age (the authoritative age), never a turn-derived proxy, or a
young character dies "of old age" purely because they lived many cheap beats.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.core.config import settings
from app.schemas.state import SessionData, ThreadState
from app.services.doom import maybe_begin_old_age_doom


def _state(*, turn: int, age: int) -> ThreadState:
    return ThreadState(session=SessionData(turn_count=turn, player_age=age))


def test_many_turns_young_character_does_not_age_out():
    # 120 turns of vignettes, age 30 — the two-speed divergence.
    st = _state(turn=120, age=30)
    assert maybe_begin_old_age_doom(st) == ""
    assert not st.doom.active


def test_triggers_on_player_age_even_at_low_turn_count():
    st = _state(turn=12, age=settings.old_age_threshold + 3)
    note = maybe_begin_old_age_doom(st)
    assert note
    assert st.doom.active and st.doom.cause == "old_age"


@given(turn=st.integers(0, 400), age=st.integers(0, 120))
def test_onset_depends_only_on_player_age(turn, age):
    """The single invariant: whether old age begins is a pure function of
    player_age vs the threshold — turn_count never enters it."""
    st = _state(turn=turn, age=age)
    fired = bool(maybe_begin_old_age_doom(st))
    assert fired == (age >= settings.old_age_threshold)
