"""Commitment 1/4 — the LLM cannot invent a broken oath (audit H1).

Lachesis's `oath_violation` is an unverified model string; `is_verifiable_violation`
is the deterministic gate deciding whether it may seal a broken-oath doom. The
load-bearing direction: with no matching active oath, NOTHING the model emits is
honored — so a bare "none" (a model tic), a hallucination, or an injection string
can never doom a player who swore nothing.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from app.schemas.state import Oath
from app.services.oath_engine import is_verifiable_violation

_ids = st.text(min_size=1, max_size=10)
_statuses = st.sampled_from(["active", "fulfilled", "broken", "transformed"])
_oaths = st.lists(
    st.builds(
        Oath,
        oath_id=_ids,
        text=st.just("x"),
        turn_sworn=st.integers(0, 60),
        status=_statuses,
    ),
    max_size=6,
)


@given(claimed=st.text(max_size=16))
@example(claimed="none")   # the classic model tic that the audit caught
@example(claimed="None")
@example(claimed="")
def test_no_active_oaths_means_no_claim_is_ever_honored(claimed):
    """The core safety: from nothing sworn, nothing the model says breaks."""
    assert is_verifiable_violation(claimed, []) is False


@given(claimed=st.text(max_size=16), oaths=_oaths)
def test_only_an_active_matching_id_is_honored(claimed, oaths):
    honored = is_verifiable_violation(claimed, oaths)
    # Honored ⇒ there is an ACTIVE oath with exactly this (non-empty) id.
    if honored:
        assert claimed
        assert any(o.oath_id == claimed and o.status == "active" for o in oaths)
    # And any id matching an active oath is always honored (the other direction).
    active_ids = {o.oath_id for o in oaths if o.status == "active"}
    if claimed in active_ids:
        assert honored is True
