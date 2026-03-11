"""Tests for SoulVectorEngine — the mathematical backbone of the Nyx Engine.

Covers: apply_deltas clamping, dominant/weakest vector, imbalance scoring,
Nemesis watch threshold, milestone detection, dead-soul detection.
"""

from app.schemas.state import SoulVectors
from app.services.soul_math import SoulVectorEngine


# ---------------------------------------------------------------------------
# apply_deltas
# ---------------------------------------------------------------------------

class TestApplyDeltas:
    def test_basic_positive_delta(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {"bia": 2.0})
        assert result.bia == 7.0
        # Others unchanged
        assert result.metis == 5.0
        assert result.kleos == 5.0
        assert result.aidos == 5.0

    def test_negative_delta(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {"aidos": -3.0})
        assert result.aidos == 2.0

    def test_clamp_upper_bound(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {"metis": 100.0})
        assert result.metis == 10.0

    def test_clamp_lower_bound(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {"bia": -50.0})
        assert result.bia == 0.0

    def test_multiple_deltas(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(
            default_vectors, {"bia": 2.0, "aidos": -1.0, "metis": 0.5}
        )
        assert result.bia == 7.0
        assert result.aidos == 4.0
        assert result.metis == 5.5
        assert result.kleos == 5.0  # untouched

    def test_unknown_key_ignored(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {"hubris": 5.0})
        # Nothing should change
        assert result == default_vectors

    def test_empty_deltas(self, default_vectors: SoulVectors):
        result = SoulVectorEngine.apply_deltas(default_vectors, {})
        assert result == default_vectors

    def test_clamp_exact_boundaries(self):
        vecs = SoulVectors(metis=0.0, bia=10.0, kleos=5.0, aidos=5.0)
        result = SoulVectorEngine.apply_deltas(vecs, {"metis": -1.0, "bia": 1.0})
        assert result.metis == 0.0  # clamped at 0
        assert result.bia == 10.0   # clamped at 10


# ---------------------------------------------------------------------------
# dominant_vector / weakest_vector
# ---------------------------------------------------------------------------

class TestDominantWeakest:
    def test_dominant_clear_winner(self, bia_dominant_vectors: SoulVectors):
        assert SoulVectorEngine.dominant_vector(bia_dominant_vectors) == "bia"

    def test_weakest_clear_loser(self, bia_dominant_vectors: SoulVectors):
        assert SoulVectorEngine.weakest_vector(bia_dominant_vectors) == "aidos"

    def test_balanced_returns_any(self, default_vectors: SoulVectors):
        # When all equal, max/min picks the first one (dict order)
        dominant = SoulVectorEngine.dominant_vector(default_vectors)
        weakest = SoulVectorEngine.weakest_vector(default_vectors)
        assert dominant in ("metis", "bia", "kleos", "aidos")
        assert weakest in ("metis", "bia", "kleos", "aidos")

    def test_milestone_dominant(self, milestone_vectors: SoulVectors):
        assert SoulVectorEngine.dominant_vector(milestone_vectors) == "metis"


# ---------------------------------------------------------------------------
# imbalance_score
# ---------------------------------------------------------------------------

class TestImbalanceScore:
    def test_balanced_soul(self, default_vectors: SoulVectors):
        assert SoulVectorEngine.imbalance_score(default_vectors) == 0.0

    def test_imbalanced_soul(self, bia_dominant_vectors: SoulVectors):
        # max=9.0 (bia), min=2.0 (aidos) → 7.0
        assert SoulVectorEngine.imbalance_score(bia_dominant_vectors) == 7.0

    def test_dead_soul_imbalance(self, dead_soul_vectors: SoulVectors):
        # max=1.0, min=0.0 → 1.0
        assert SoulVectorEngine.imbalance_score(dead_soul_vectors) == 1.0

    def test_extreme_imbalance(self):
        vecs = SoulVectors(metis=0.0, bia=10.0, kleos=0.0, aidos=0.0)
        assert SoulVectorEngine.imbalance_score(vecs) == 10.0


# ---------------------------------------------------------------------------
# should_nemesis_watch
# ---------------------------------------------------------------------------

class TestNemesisWatch:
    def test_balanced_no_watch(self, default_vectors: SoulVectors):
        assert SoulVectorEngine.should_nemesis_watch(default_vectors) is False

    def test_imbalanced_triggers_watch(self, bia_dominant_vectors: SoulVectors):
        # imbalance = 7.0 ≥ threshold 6.0
        assert SoulVectorEngine.should_nemesis_watch(bia_dominant_vectors) is True

    def test_custom_threshold(self, bia_dominant_vectors: SoulVectors):
        # imbalance = 7.0 < threshold 8.0
        assert SoulVectorEngine.should_nemesis_watch(bia_dominant_vectors, threshold=8.0) is False

    def test_exact_threshold(self):
        vecs = SoulVectors(metis=0.0, bia=6.0, kleos=3.0, aidos=3.0)
        # imbalance = 6.0, threshold = 6.0 → True (>=)
        assert SoulVectorEngine.should_nemesis_watch(vecs) is True


# ---------------------------------------------------------------------------
# is_milestone
# ---------------------------------------------------------------------------

class TestMilestone:
    def test_no_milestone(self, default_vectors: SoulVectors):
        hit, name = SoulVectorEngine.is_milestone(default_vectors)
        assert hit is False
        assert name == ""

    def test_milestone_hit(self, milestone_vectors: SoulVectors):
        hit, name = SoulVectorEngine.is_milestone(milestone_vectors)
        assert hit is True
        assert name == "metis"

    def test_just_below_milestone(self):
        vecs = SoulVectors(metis=9.99, bia=5.0, kleos=5.0, aidos=5.0)
        hit, _ = SoulVectorEngine.is_milestone(vecs)
        assert hit is False

    def test_multiple_milestones_returns_first(self):
        vecs = SoulVectors(metis=10.0, bia=10.0, kleos=5.0, aidos=5.0)
        hit, name = SoulVectorEngine.is_milestone(vecs)
        assert hit is True
        assert name in ("metis", "bia")  # first found in dict order


# ---------------------------------------------------------------------------
# is_dead_soul
# ---------------------------------------------------------------------------

class TestDeadSoul:
    def test_not_dead(self, default_vectors: SoulVectors):
        assert SoulVectorEngine.is_dead_soul(default_vectors) is False

    def test_dead_soul(self, dead_soul_vectors: SoulVectors):
        assert SoulVectorEngine.is_dead_soul(dead_soul_vectors) is True

    def test_one_vector_above_threshold(self):
        vecs = SoulVectors(metis=0.5, bia=0.5, kleos=0.5, aidos=1.5)
        assert SoulVectorEngine.is_dead_soul(vecs) is False

    def test_all_exactly_one(self):
        vecs = SoulVectors(metis=1.0, bia=1.0, kleos=1.0, aidos=1.0)
        assert SoulVectorEngine.is_dead_soul(vecs) is True

    def test_all_zero(self):
        vecs = SoulVectors(metis=0.0, bia=0.0, kleos=0.0, aidos=0.0)
        assert SoulVectorEngine.is_dead_soul(vecs) is True


# ---------------------------------------------------------------------------
# vector_summary
# ---------------------------------------------------------------------------

class TestVectorSummary:
    def test_summary_format(self, default_vectors: SoulVectors):
        summary = SoulVectorEngine.vector_summary(default_vectors)
        assert "metis=5.0" in summary
        assert "bia=5.0" in summary
        assert "|" in summary
