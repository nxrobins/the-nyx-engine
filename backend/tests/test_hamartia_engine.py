"""Tests for the Hamartia Engine — deterministic tragic flaw assignment.

Extracted from TestDetermineHamartia in test_lachesis.py (P1-002).
"""

from app.schemas.state import SoulVectors, ThreadState
from app.services.hamartia_engine import (
    HAMARTIA_PROFILES,
    VECTOR_HAMARTIA_MAP,
    _VOICE_BY_FLAW,
    _VOICE_GARNISH,
    determine_hamartia,
    get_hamartia_profile,
    get_life_voice,
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


class TestGetLifeVoice:
    """get_life_voice() derives the Scribe's narrative register: a flaw-keyed
    base + a dominant-vector garnish, discovered once at the Fork. Pure and
    deterministic — these lock the mapping so a copy edit can't silently
    rewrite an incarnation's voice, and a tie can't drift.
    """

    @staticmethod
    def _state(metis=0.0, bia=0.0, kleos=0.0, aidos=0.0) -> ThreadState:
        state = ThreadState()
        state.soul_ledger.vectors = SoulVectors(metis=metis, bia=bia, kleos=kleos, aidos=aidos)
        return state

    def test_each_flaw_selects_its_registered_base(self):
        # The flaw picks the register; substring match, case-insensitive.
        for flaw in ("hubris", "wrath", "vainglory", "cowardice"):
            voice = get_life_voice(flaw.upper(), self._state(metis=1.0))
            assert voice.startswith(_VOICE_BY_FLAW[flaw]), flaw

    def test_flaw_matches_as_a_substring_of_a_verbose_label(self):
        # Real labels are verbose ("Cowardice Veiled as Wisdom"); the key still hits.
        voice = get_life_voice("Cowardice Veiled as Wisdom", self._state(metis=1.0))
        assert voice.startswith(_VOICE_BY_FLAW["cowardice"])

    def test_unknown_flaw_falls_back_to_the_plain_voice(self):
        voice = get_life_voice("Serenity", self._state(kleos=1.0))
        assert voice.startswith("Plain, weathered, declarative")

    def test_each_dominant_vector_appends_its_garnish(self):
        for vec in ("metis", "bia", "kleos", "aidos"):
            voice = get_life_voice("wrath", self._state(**{vec: 9.0}))
            assert voice.endswith(_VOICE_GARNISH[vec]), vec

    def test_a_tie_resolves_deterministically_to_metis(self):
        # All-zero vectors: max() keeps the first pair, which is metis. The voice
        # must never depend on dict/iteration luck.
        voice = get_life_voice("Unformed", self._state())
        assert voice.endswith(_VOICE_GARNISH["metis"])

    def test_voice_is_base_then_garnish_joined_and_stripped(self):
        state = self._state(bia=5.0)
        voice = get_life_voice("hubris", state)
        assert voice == f"{_VOICE_BY_FLAW['hubris']} {_VOICE_GARNISH['bia']}"
        assert voice == voice.strip()

    def test_is_deterministic_for_identical_inputs(self):
        a = get_life_voice("hubris", self._state(metis=3.0, kleos=1.0))
        b = get_life_voice("hubris", self._state(metis=3.0, kleos=1.0))
        assert a == b
