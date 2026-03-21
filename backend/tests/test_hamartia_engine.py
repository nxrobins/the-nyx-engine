"""Tests for the Hamartia Engine — deterministic tragic flaw assignment.

Extracted from TestDetermineHamartia in test_lachesis.py (P1-002).
"""

from app.schemas.state import SoulVectors, ThreadState
from app.services.hamartia_engine import (
    HAMARTIA_PROFILES,
    VECTOR_HAMARTIA_MAP,
    determine_hamartia,
    get_hamartia_profile,
)


class TestDetermineHamartia:
    """determine_hamartia() assigns tragic flaw from dominant soul vector."""

    def test_metis_dominant(self, unformed_turn10_state: ThreadState):
        # metis=8.0 is dominant
        result = determine_hamartia(unformed_turn10_state)
        assert result == "Hubris"

    def test_bia_dominant(self, unformed_turn10_state: ThreadState):
        unformed_turn10_state.soul_ledger.vectors = SoulVectors(
            metis=3.0, bia=9.0, kleos=4.0, aidos=2.0
        )
        result = determine_hamartia(unformed_turn10_state)
        assert result == "Wrath"

    def test_kleos_dominant(self, unformed_turn10_state: ThreadState):
        unformed_turn10_state.soul_ledger.vectors = SoulVectors(
            metis=3.0, bia=4.0, kleos=9.0, aidos=2.0
        )
        result = determine_hamartia(unformed_turn10_state)
        assert result == "Vainglory"

    def test_aidos_dominant(self, unformed_turn10_state: ThreadState):
        unformed_turn10_state.soul_ledger.vectors = SoulVectors(
            metis=3.0, bia=2.0, kleos=4.0, aidos=9.0
        )
        result = determine_hamartia(unformed_turn10_state)
        assert result == "Cowardice"

    def test_already_assigned_returns_none(self, mid_game_state: ThreadState):
        # hamartia is "Wrath of the Untempered", not "Unformed"
        result = determine_hamartia(mid_game_state)
        assert result is None

    def test_wrong_epoch_returns_none(self, unformed_turn10_state: ThreadState):
        unformed_turn10_state.session.epoch_phase = 2  # not phase 4
        result = determine_hamartia(unformed_turn10_state)
        assert result is None

    def test_requires_both_conditions(self, fresh_state: ThreadState):
        # Fresh state: hamartia="" (not "Unformed"), epoch_phase=1
        result = determine_hamartia(fresh_state)
        assert result is None


class TestVectorHamartiaMap:
    """The mapping covers all four soul vectors."""

    def test_all_vectors_mapped(self):
        assert set(VECTOR_HAMARTIA_MAP.keys()) == {"metis", "bia", "kleos", "aidos"}

    def test_all_values_are_strings(self):
        for v in VECTOR_HAMARTIA_MAP.values():
            assert isinstance(v, str)
            assert len(v) > 0


class TestHamartiaProfiles:
    """Profiles turn a flaw into a live mechanical bias."""

    def test_profile_lookup_matches_simple_label(self):
        profile = get_hamartia_profile("Wrath")
        assert profile is not None
        assert profile.name == "Wrath"
        assert profile.nemesis_multiplier > 1.0

    def test_profile_lookup_matches_verbose_label(self):
        profile = get_hamartia_profile("Cowardice Veiled as Wisdom")
        assert profile is not None
        assert profile.name == "Cowardice"
        assert "avoidance" in profile.choice_bias

    def test_profiles_cover_core_hamartiai(self):
        assert {"hubris", "wrath", "vainglory", "cowardice"} <= set(HAMARTIA_PROFILES.keys())
