"""Commitment 1 (consequence is law) — soul-vector math invariants.

The four soul vectors are the spine of the consequence economy: imbalance drives
Nemesis, total collapse is death, a maxed vector is a milestone. Every one of
those reads assumes the vectors are ALWAYS within [0, 10] — no delta sequence,
however adversarial (unknown keys, extreme magnitudes, the kind of thing a
degraded model or a bug could hand the engine), may push a vector out of range
or make the derived reads throw.

These pin that invariant under generation rather than by a handful of examples.
This is also the foundation slice's harness-prover: the clamp is already correct
(audit-confirmed), so a green run demonstrates the Hypothesis harness works
without shipping a red test.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.schemas.state import SoulVectors
from app.services.soul_math import SoulVectorEngine

_VNAMES = ("metis", "bia", "kleos", "aidos")

# A soul: any four vectors already in the legal range.
_souls = st.builds(
    SoulVectors,
    metis=st.floats(0, 10),
    bia=st.floats(0, 10),
    kleos=st.floats(0, 10),
    aidos=st.floats(0, 10),
)

# A delta packet: arbitrary finite floats keyed by real vector names AND junk
# keys the engine must ignore — the shape a model or a bug could emit.
_deltas = st.dictionaries(
    keys=st.sampled_from((*_VNAMES, "unknown", "hp", "")),
    values=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    max_size=6,
)


@given(_souls, st.lists(_deltas, max_size=8))
def test_vectors_stay_in_range_under_any_delta_sequence(soul, packets):
    """apply_deltas clamps to [0, 10] no matter the packet or how many are chained."""
    for packet in packets:
        soul = SoulVectorEngine.apply_deltas(soul, packet)
        for name in _VNAMES:
            v = getattr(soul, name)
            assert 0.0 <= v <= 10.0, f"{name}={v} escaped [0,10] after {packet}"


@given(_souls)
def test_imbalance_score_is_bounded_and_nonnegative(soul):
    """imbalance = max - min: always within its documented [0, 10] range."""
    score = SoulVectorEngine.imbalance_score(soul)
    assert 0.0 <= score <= 10.0


@given(_souls, _deltas)
def test_derived_reads_are_total(soul, packet):
    """The reads Nemesis/Atropos depend on never raise for any in-range soul."""
    soul = SoulVectorEngine.apply_deltas(soul, packet)
    assert SoulVectorEngine.dominant_vector(soul) in _VNAMES
    assert SoulVectorEngine.weakest_vector(soul) in _VNAMES
    is_ms, name = SoulVectorEngine.is_milestone(soul)
    assert isinstance(is_ms, bool) and (name in _VNAMES or name == "")
    assert isinstance(SoulVectorEngine.is_dead_soul(soul), bool)
