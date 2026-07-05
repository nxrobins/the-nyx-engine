"""Commitment 2 (a life is a book) — the two-speed beat scheduler (P1-C1/C10).

THE PULSE's scheduler is the pacing law of the whole reorientation: chapters are
age-scaled runs of vignettes capped by exactly one crucible, drama can fire the
crucible early, and a chapter close is the (one) dream boundary. These pin the
law under generation before the kernel wires it (sub-slice 3).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.core.director import (
    CHAPTER_BUDGET_MAX,
    CRUCIBLE,
    VIGNETTE,
    chapter_budget,
    next_beat_kind,
    record_beat,
)
from app.schemas.state import (
    DoomState,
    SceneClock,
    SceneState,
    ThreadState,
    WorldCanon,
)


def _quiet_state(age: int, beats_spent: int = 0) -> ThreadState:
    """A state with no early-trigger drama: scheduling is pure budget."""
    s = ThreadState()
    s.session.player_age = age
    s.session.beats_spent = beats_spent
    return s


def _state_with_maturing_clock(age: int) -> ThreadState:
    s = _quiet_state(age)
    clock = SceneClock(clock_id="clk", label="the road closes", progress=3, max_segments=4)
    s.canon = WorldCanon(
        clocks={"clk": clock},
        current_scene=SceneState(scene_id="sc", location_id="loc", active_clock_ids=["clk"]),
    )
    return s


# ── P1-C1: the age curve ─────────────────────────────────────────────────────

@given(age=st.integers(0, 120))
def test_budget_is_bounded_by_the_hard_max(age):
    assert 0 <= chapter_budget(age) <= CHAPTER_BUDGET_MAX


@given(younger=st.integers(0, 120), older=st.integers(0, 120))
def test_budget_is_monotone_in_age(younger, older):
    """Nigel's ruling: chapters grow as the character ages — never shrink."""
    if younger <= older:
        assert chapter_budget(younger) <= chapter_budget(older)


@given(age=st.integers(0, 3))
def test_birth_chapter_is_its_single_beat(age):
    """A birth chapter is one crucible-grade beat: zero vignettes budgeted."""
    assert chapter_budget(age) == 0
    assert next_beat_kind(_quiet_state(age)) == CRUCIBLE


# ── Early triggers outrank the budget ────────────────────────────────────────

@given(age=st.integers(0, 120), beats=st.integers(0, 5))
def test_active_doom_forces_a_crucible(age, beats):
    s = _quiet_state(age, beats)
    s.doom = DoomState(active=True, cause="wounds", stage=1)
    assert next_beat_kind(s) == CRUCIBLE


@given(age=st.integers(0, 120))
def test_maturing_clock_forces_a_crucible(age):
    assert next_beat_kind(_state_with_maturing_clock(age)) == CRUCIBLE


# ── Determinism ──────────────────────────────────────────────────────────────

@given(age=st.integers(0, 120), beats=st.integers(0, 8), doomed=st.booleans())
def test_same_state_same_beat(age, beats, doomed):
    s = _quiet_state(age, beats)
    if doomed:
        s.doom = DoomState(active=True, cause="wounds", stage=1)
    assert next_beat_kind(s) == next_beat_kind(s)


# ── The chapter law: budget exactly spent, crucible closes, never a 7th beat ─

@given(age=st.integers(4, 120), chapters=st.integers(1, 4))
def test_quiet_chapters_run_exactly_their_budget_then_close(age, chapters):
    """Simulate whole quiet chapters through the scheduler+bookkeeping loop:
    each runs exactly budget(age) vignettes, then one crucible that closes it
    (the dream boundary), resetting the spend. No sequence exceeds the hard max
    (P1-C1) and every chapter has exactly one close (P1-C10)."""
    s = _quiet_state(age)
    budget = chapter_budget(age)
    closes = 0
    for _ in range(chapters):
        vignettes_this_chapter = 0
        # safety bound: a chapter can never take more than budget+1 beats
        for _beat in range(budget + 1):
            kind = next_beat_kind(s)
            closed = record_beat(s.session, kind)
            if kind == VIGNETTE:
                vignettes_this_chapter += 1
                assert not closed
            else:
                assert closed  # a crucible ALWAYS closes the chapter
                closes += 1
                break
        assert vignettes_this_chapter == budget          # ceiling exactly spent when quiet
        assert vignettes_this_chapter <= CHAPTER_BUDGET_MAX
        assert s.session.beats_spent == 0                # reset for the next chapter
    assert closes == chapters                             # one dream boundary per chapter
    assert s.session.chapter_index == chapters


@given(kind=st.sampled_from([VIGNETTE, CRUCIBLE]))
def test_record_beat_bookkeeping(kind):
    s = _quiet_state(30)
    s.session.beats_spent = 2
    s.session.chapter_index = 3
    closed = record_beat(s.session, kind)
    assert s.session.beat_kind == kind
    if kind == CRUCIBLE:
        assert closed and s.session.chapter_index == 4 and s.session.beats_spent == 0
    else:
        assert not closed and s.session.chapter_index == 3 and s.session.beats_spent == 3
