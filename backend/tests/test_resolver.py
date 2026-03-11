"""Tests for ConflictResolver — the 4-tier hierarchy that prevents agent deadlock.

Tier 1: Lachesis (state validity) — invalid action mutes everything
Tier 2: Atropos (finality) — death overrides, unless Eris miracle
Tier 3: Nemesis vs Eris — imbalance tiebreaker
Tier 4: Clean pass to Clotho
"""

from app.core.resolver import ConflictResolver, ResolvedOutcome
from app.schemas.state import (
    AtroposResponse,
    ErisResponse,
    LachesisResponse,
    NemesisResponse,
    SoulVectors,
    ThreadState,
)


class TestTier1Lachesis:
    """Tier 1: If Lachesis says invalid, everything else is muted."""

    def test_invalid_action_blocks_all(
        self,
        mid_game_state: ThreadState,
        invalid_lachesis: LachesisResponse,
        terminal_atropos: AtroposResponse,
        nemesis_punishment: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, invalid_lachesis, terminal_atropos,
            nemesis_punishment, eris_chaos,
        )
        assert outcome.action_valid is False
        assert outcome.terminal is False  # death suppressed
        assert outcome.nemesis_struck is False
        assert outcome.eris_struck is False
        assert "mortal" in outcome.invalid_reason.lower()

    def test_valid_action_passes_tier1(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_silent: ErisResponse,
    ):
        # Set updated_state so resolver has a base to work from
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_silent, eris_silent,
        )
        assert outcome.action_valid is True
        assert outcome.terminal is False


class TestTier2Atropos:
    """Tier 2: Atropos death overrides, unless Eris miracle saves."""

    def test_death_without_eris(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        terminal_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_silent: ErisResponse,
    ):
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, terminal_atropos,
            nemesis_silent, eris_silent,
        )
        assert outcome.terminal is True
        assert "void" in outcome.death_reason.lower()

    def test_eris_miracle_saves_balanced_soul(
        self,
        fresh_state: ThreadState,
        valid_lachesis: LachesisResponse,
        terminal_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        """Balanced soul (imbalance=0 < threshold=6) + Eris triggered = miracle."""
        valid_lachesis.updated_state = fresh_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            fresh_state, valid_lachesis, terminal_atropos,
            nemesis_silent, eris_chaos,
        )
        assert outcome.terminal is False  # saved!
        assert outcome.eris_struck is True
        assert "chaos" in outcome.eris_description.lower() or "death" in outcome.eris_description.lower()

    def test_no_miracle_for_imbalanced_soul(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        terminal_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        """Imbalanced soul (bia=7.5, aidos=3.0 → imbalance=4.5) needs to be
        compared against threshold. With threshold=6.0, imbalance=4.5 < 6.0,
        so miracle DOES fire. Let's force high imbalance instead."""
        # Override to very imbalanced soul
        mid_game_state.soul_ledger.vectors = SoulVectors(
            metis=1.0, bia=9.0, kleos=1.0, aidos=1.0
        )
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, terminal_atropos,
            nemesis_silent, eris_chaos,
        )
        # imbalance = 8.0 ≥ threshold 6.0 → no miracle
        assert outcome.terminal is True


class TestTier3NemesisVsEris:
    """Tier 3: When both Nemesis and Eris fire, imbalance tiebreaker decides."""

    def test_nemesis_wins_imbalanced_soul(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_punishment: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        """High imbalance → W_c > 0 → Nemesis wins."""
        mid_game_state.soul_ledger.vectors = SoulVectors(
            metis=2.0, bia=9.0, kleos=3.0, aidos=1.0
        )
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_punishment, eris_chaos,
        )
        # imbalance = 8.0, threshold = 6.0 → W_c = 2.0 > 0 → Nemesis
        assert outcome.nemesis_struck is True
        assert outcome.eris_struck is False
        assert outcome.vector_penalty == {"bia": -2.0, "kleos": -1.0}

    def test_eris_wins_balanced_soul(
        self,
        fresh_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_punishment: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        """Balanced soul → W_c ≤ 0 → Eris wins."""
        valid_lachesis.updated_state = fresh_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            fresh_state, valid_lachesis, alive_atropos,
            nemesis_punishment, eris_chaos,
        )
        # imbalance = 0.0, threshold = 6.0 → W_c = -6.0 ≤ 0 → Eris
        assert outcome.eris_struck is True
        assert outcome.nemesis_struck is False

    def test_nemesis_only(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_punishment: NemesisResponse,
        eris_silent: ErisResponse,
    ):
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_punishment, eris_silent,
        )
        assert outcome.nemesis_struck is True
        assert outcome.eris_struck is False

    def test_eris_only(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_chaos: ErisResponse,
    ):
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_silent, eris_chaos,
        )
        assert outcome.eris_struck is True
        assert outcome.nemesis_struck is False

    def test_lethal_nemesis_marks_oath_broken(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_lethal: NemesisResponse,
        eris_silent: ErisResponse,
    ):
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_lethal, eris_silent,
        )
        assert outcome.nemesis_struck is True
        assert outcome.oath_broken is True
        assert outcome.nemesis_type == "lethal_punishment"


class TestTier4CleanPass:
    """Tier 4: Nothing fires — clean pass-through."""

    def test_clean_pass(
        self,
        mid_game_state: ThreadState,
        valid_lachesis: LachesisResponse,
        alive_atropos: AtroposResponse,
        nemesis_silent: NemesisResponse,
        eris_silent: ErisResponse,
    ):
        valid_lachesis.updated_state = mid_game_state

        resolver = ConflictResolver()
        outcome = resolver.resolve(
            mid_game_state, valid_lachesis, alive_atropos,
            nemesis_silent, eris_silent,
        )
        assert outcome.action_valid is True
        assert outcome.terminal is False
        assert outcome.nemesis_struck is False
        assert outcome.eris_struck is False
        assert outcome.state is mid_game_state


class TestResolvedOutcomeDefaults:
    """Ensure ResolvedOutcome dataclass defaults are sane."""

    def test_defaults(self, fresh_state: ThreadState):
        outcome = ResolvedOutcome(state=fresh_state)
        assert outcome.action_valid is True
        assert outcome.terminal is False
        assert outcome.nemesis_struck is False
        assert outcome.eris_struck is False
        assert outcome.invalid_reason == ""
        assert outcome.death_reason == ""
        assert outcome.vector_penalty == {}
        assert outcome.vector_chaos == {}
        assert outcome.oath_broken is False
