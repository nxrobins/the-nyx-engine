"""The Innocence Suite (v0) — Commitment 1: only earned deaths (audit H3).

The FICTION self-destruction trigger matched keywords as bare substrings with no
negation guard, so "I will never give up completely" read as a death wish — a
permanent, non-miracleable death by accident. `expresses_self_destruction` now
matches whole phrases and refuses a negated one. This suite generates the classes
the guard fixes and pins the audit's real false positives as @example seeds.

SCOPE + a surfaced limitation: the keyword *content* (e.g. the generic "jump off",
which still fires on "I jump off the cart") is coupled to the real-human crisis
detector by the SAFE-C4 invariant and is NOT changed here — narrowing it is a
Vigil decision for Nigel (see the-shelf.md checkpoints). So this suite asserts
what the matching guard delivers (negation-awareness, whole-phrase, benign
non-keyword actions), not the generic-keyword case.

The real-human crisis detector (services/welfare.py) is a separate, deliberately
liberal, fail-safe surface and stays raw-substring by design; it is tested apart.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from app.agents.atropos import expresses_self_destruction
from app.core.config import settings

_KEYWORDS = settings.atropos_death_keywords
_NEGATORS = ["I will never", "I won't", "I refuse to", "I would never", "I don't", "I can't"]

# Ordinary play that shares no whole keyword phrase — must never trip the trigger.
_BENIGN = [
    "I walk to the market and buy bread",
    "I grab the rope and climb down",
    "I hide behind the wall and wait",
    "I give the elder my last coin",
    "I look into the well",
    "I end the argument and leave",
    "I drink the water from the stream",
    "I cut the bread for my mother",
    "I run up the hill toward the gate",
    "I jump off the cart and run",        # the audit's headline — now a benign leap
    "I jump off the log into the grass",
    "I leap off the step and keep going",
]

# Genuine leaps toward a lethal target — the fiction death IS earned here.
_LETHAL_LEAPS = [
    "I climb up and jump off a cliff",
    "I jump off the bridge into the dark",
    "I throw myself off the tower",
    "I leap from the roof to my death",
]


@given(neg=st.sampled_from(_NEGATORS), kw=st.sampled_from(_KEYWORDS))
@example(neg="I will never", kw="give up completely")   # the audit's headline negation
@example(neg="I refuse to", kw="surrender to death")
def test_negated_intent_never_triggers_fiction_death(neg, kw):
    assert expresses_self_destruction(f"{neg} {kw}.", _KEYWORDS) is False


@given(action=st.sampled_from(_BENIGN))
def test_benign_non_keyword_actions_never_trigger(action):
    assert expresses_self_destruction(action, _KEYWORDS) is False


@given(kw=st.sampled_from(_KEYWORDS))
def test_explicit_unnegated_intent_still_triggers(kw):
    """The guard is conservative, not disabled: genuine intent still kills."""
    assert expresses_self_destruction(f"I {kw} now.", _KEYWORDS) is True


@given(action=st.sampled_from(_LETHAL_LEAPS))
def test_lethal_leaps_are_earned_deaths(action):
    """A leap toward a lethal target IS self-destruction (death-context rule)."""
    assert expresses_self_destruction(action, _KEYWORDS) is True
