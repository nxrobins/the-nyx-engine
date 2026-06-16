"""The Long Road Home — old-age mortality (depth axis).

A long, UNDOOMED thread finally bends toward a natural close. Pure/deterministic;
the doom slots into the existing state machine with no new Atropos/resolver wiring.
The "no instant sever" guarantee is a KERNEL-ordering property (the doom begins at
step 8b, after Atropos's step-4 read), so it is proven by an integration turn here.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.schemas.state import DoomState, SessionData, ThreadState
from app.services.doom import (
    begin_doom,
    doom_death_reason,
    maybe_begin_old_age_doom,
)


def _state(turn: int) -> ThreadState:
    return ThreadState(session=SessionData(turn_count=turn))


def _turn_for_age(age: int) -> int:
    # age = 18 + (turn_count - 10)  ->  turn_count = age - 8
    return age - 8


class TestOnset:
    def test_below_threshold_begins_nothing(self):
        st = _state(_turn_for_age(settings.old_age_threshold - 1))
        assert maybe_begin_old_age_doom(st) == ""
        assert not st.doom.active

    def test_at_threshold_begins_inescapable_stage_one(self):
        st = _state(_turn_for_age(settings.old_age_threshold))
        note = maybe_begin_old_age_doom(st)
        assert note
        assert st.doom.active and st.doom.cause == "old_age"
        assert st.doom.escapable is False        # the years cannot be answered
        assert st.doom.stage == 1                 # begun at stage 1, always
        assert st.doom.max_stage == 3             # full runway at the threshold

    def test_max_stage_shrinks_with_age_but_never_below_one(self):
        thr = settings.old_age_threshold
        for age, expected in [(thr, 3), (thr + 9, 3), (thr + 10, 2), (thr + 20, 1), (thr + 99, 1)]:
            st = _state(_turn_for_age(age))
            maybe_begin_old_age_doom(st)
            assert st.doom.max_stage == expected, (age, st.doom.max_stage)
            assert st.doom.max_stage >= 1         # the floor — decline is never instant

    def test_yields_to_an_active_acute_doom(self):
        # OLD-AG-2: an old man bleeding out dies OF the wound (escapable, with its
        # visible escape) — never silently relabelled to "old_age".
        st = _state(_turn_for_age(settings.old_age_threshold + 15))
        begin_doom(st, cause="wounds", description="bleeding", max_stage=3, escapable=True)
        assert maybe_begin_old_age_doom(st) == ""
        assert st.doom.cause == "wounds" and st.doom.escapable is True


class TestDeathReason:
    def test_death_is_authored_not_the_onset_murmur(self):
        # OLD-C1: the final words are a closing line, not the onset description.
        st = _state(200)
        st.doom = DoomState(
            active=True, cause="old_age",
            description="The body has carried you a long way, and it is tiring.",
            stage=1, max_stage=1,
        )
        reason = doom_death_reason(st)
        assert "sets its burden down" in reason       # the authored close
        assert "it is tiring" not in reason            # NOT the onset murmur


class TestConfig:
    def test_threshold_stays_an_adult_age(self):
        # OLD-AG-1: below 18 the self-contained age formula would diverge from
        # the childhood _AGE_MAP; the gate must keep that out of range.
        assert settings.old_age_threshold >= 18

    def test_sub_adult_threshold_is_rejected_at_load(self):
        # OLD-AG-1 is now ENFORCED, not just asserted: an env/init override below
        # 18 fails closed instead of silently re-enabling childhood old-age death.
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(old_age_threshold=10)

    def test_adult_threshold_is_accepted(self):
        from app.core.config import Settings

        assert Settings(old_age_threshold=18).old_age_threshold == 18


class TestKernelOrdering:
    @pytest.mark.asyncio
    async def test_onset_turn_survives_then_severs_next_turn(self, monkeypatch):
        """OLD-C2: the doom begins at step 8b (after Atropos's step-4 read), so the
        onset turn is NOT terminal even at the max_stage=1 floor — exactly one lived
        turn — then Atropos collects on the following turn with the authored close."""
        # Pin a LOW threshold so deep old age (max_stage=1) is reached at a low
        # turn_count — keeping the Scribe death-book's epoch_index (turn//3) well
        # under its schema cap; the real game crosses age slowly over many turns.
        monkeypatch.setattr(settings, "old_age_threshold", 20)
        # Pin Eris's chaos roll OFF deterministically. A balanced soul + a chaos
        # roll can MIRACLE the sever for one turn (the Eris valve — OLD-AG-4):
        # correct soul behaviour, but it makes the exact death turn
        # nondeterministic, and this test asserts the sever itself. NOTE:
        # eris_chaos_probability=0.0 does NOT silence the valve — eris.py floors
        # the effective chance at 0.02 and the suite never seeds `random`, so the
        # roll can still fire under test reordering. Pin the module RNG high
        # instead, the same guard test_doom/test_legacy use for exactly this.
        import app.agents.eris as eris_module
        monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)
        k = NyxKernel()
        await k.initialize(
            hamartia="Unformed", player_id="road", name="Methuselah", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        # age 40 with threshold 20 -> max_stage floors at 1 (the worst case).
        k.state.session.turn_count = _turn_for_age(40)

        onset = await k.process_turn("rest by the fire")
        assert not onset.terminal                      # survived the onset turn
        assert k.state.doom.active and k.state.doom.cause == "old_age"

        after = await k.process_turn("rest a while longer")
        assert after.terminal                          # the long road ends
        assert "sets its burden down" in after.death_reason
