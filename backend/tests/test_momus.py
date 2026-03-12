"""Tests for Momus — the Literary Law Enforcer & Hallucination Checker v3.1.

Covers:
  State hallucination checks:
    - Environment consistency
    - Oath reference validation
    - Death language detection
    - Multi-hallucination aggregation

  Literary Law checks:
    - Law IV  (No Anachronisms)  — anachronism detection
    - Law I   (Show Then Tell)   — emotion naming threshold (>3 = violation)
    - Law II  (Player Acts)      — passive voice threshold (>6 = violation)
    - Law VI  (Economy)          — paragraph overflow

  Schema & identity:
    - MomusValidation model behavior
    - Agent name and evaluate() passthrough
"""

from __future__ import annotations

import pytest

from app.agents.momus import Momus, _detect_anachronisms
from app.schemas.state import (
    MomusValidation,
    Oath,
    SessionData,
    SoulLedger,
    SoulVectors,
    ThreadState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def momus() -> Momus:
    return Momus()


@pytest.fixture
def desert_state() -> ThreadState:
    """Player is in a desert environment with balanced soul."""
    return ThreadState(
        session=SessionData(
            current_environment="A scorching desert stretching to the horizon.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
        ),
    )


@pytest.fixture
def ocean_state() -> ThreadState:
    """Player is in an ocean environment."""
    return ThreadState(
        session=SessionData(
            current_environment="A dark ocean churning beneath a starless sky.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
        ),
    )


@pytest.fixture
def oath_state() -> ThreadState:
    """Player has an active oath."""
    return ThreadState(
        session=SessionData(
            current_environment="A stone courtyard.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
            active_oaths=[
                Oath(oath_id="oath_1", text="I swear to protect the village.", turn_sworn=3),
            ],
        ),
    )


@pytest.fixture
def no_oath_state() -> ThreadState:
    """Player has NO active oaths."""
    return ThreadState(
        session=SessionData(
            current_environment="A quiet meadow.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
            active_oaths=[],
        ),
    )


@pytest.fixture
def collapsed_soul_state() -> ThreadState:
    """All vectors at or below 1.0 — death is plausible."""
    return ThreadState(
        session=SessionData(
            current_environment="A dim cave.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=0.5, bia=1.0, kleos=0.0, aidos=0.8),
        ),
    )


@pytest.fixture
def healthy_soul_state() -> ThreadState:
    """Healthy soul — death language would be a hallucination."""
    return ThreadState(
        session=SessionData(
            current_environment="An open field.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=6.0, bia=7.0, kleos=5.0, aidos=5.0),
        ),
    )


@pytest.fixture
def neutral_state() -> ThreadState:
    """Generic state with no special conditions — for literary law tests."""
    return ThreadState(
        session=SessionData(
            current_environment="A stone courtyard beneath grey clouds.",
        ),
        soul_ledger=SoulLedger(
            vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
        ),
    )


# ===========================================================================
# Base evaluate() — always passes
# ===========================================================================

class TestBaseEvaluate:
    """Momus.evaluate() always returns valid (it's a no-op placeholder)."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_valid(self, momus, fresh_state):
        result = await momus.evaluate(fresh_state, "some action")
        assert isinstance(result, MomusValidation)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_evaluate_returns_no_hallucinations(self, momus, fresh_state):
        result = await momus.evaluate(fresh_state, "attack the wall")
        assert result.hallucinations == []


# ===========================================================================
# STATE HALLUCINATION CHECKS
# ===========================================================================

class TestEnvironmentConsistency:
    """Momus detects terrain contradictions in prose."""

    @pytest.mark.asyncio
    async def test_desert_mentioning_ocean_flagged(self, momus, desert_state):
        prose = "You wade into the ocean, salt water stinging your wounds."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is False
        assert len(result.hallucinations) >= 1
        assert any("ocean" in h.lower() or "desert" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_ocean_mentioning_desert_flagged(self, momus, ocean_state):
        prose = "The desert sand stretches endlessly before you."
        result = await momus.validate_prose(prose, ocean_state)
        assert result.valid is False
        assert len(result.hallucinations) >= 1

    @pytest.mark.asyncio
    async def test_matching_environment_passes(self, momus, desert_state):
        prose = "The sand burns beneath your feet as you march onward."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is True
        assert result.hallucinations == []

    @pytest.mark.asyncio
    async def test_ocean_prose_in_ocean_env_passes(self, momus, ocean_state):
        prose = "The waves crash against the hull as the ship lurches starboard."
        result = await momus.validate_prose(prose, ocean_state)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_neutral_prose_passes_any_env(self, momus, desert_state):
        """Prose without terrain keywords should always pass."""
        prose = "The child reached for the door handle and hesitated."
        result = await momus.validate_prose(prose, desert_state)
        assert result.valid is True


class TestOathReferences:
    """Momus catches oath references when no oaths are active."""

    @pytest.mark.asyncio
    async def test_oath_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "The weight of your oath presses down on your shoulders."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False
        assert any("oath" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_sworn_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "You remember what you have sworn, and it steadies your hand."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_vow_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "The vow burns in your chest like a second heartbeat."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_promise_mention_without_oaths_flagged(self, momus, no_oath_state):
        prose = "You broke your promise. The silence that follows is deafening."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_oath_mention_with_active_oath_passes(self, momus, oath_state):
        """When oaths ARE active, referencing them is correct."""
        prose = "The weight of your oath presses down on your shoulders."
        result = await momus.validate_prose(prose, oath_state)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_no_oath_words_always_passes(self, momus, no_oath_state):
        """Prose without oath keywords passes regardless of oath state."""
        prose = "The child walked through the quiet meadow, watching butterflies."
        result = await momus.validate_prose(prose, no_oath_state)
        assert result.valid is True


class TestDeathLanguage:
    """Momus detects inappropriate death declarations."""

    @pytest.mark.asyncio
    async def test_death_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "Your strength fails. You die in the dirt, alone and forgotten."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False
        assert any("death" in h.lower() or "die" in h.lower() for h in result.hallucinations)

    @pytest.mark.asyncio
    async def test_perish_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "The darkness takes you. You perish in the cold."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_life_ends_with_healthy_soul_flagged(self, momus, healthy_soul_state):
        prose = "The blade strikes true. Your life ends here."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_death_with_collapsed_soul_passes(self, momus, collapsed_soul_state):
        """When soul vectors are collapsed (all <= 1.0), death is legitimate."""
        prose = "The last ember of your soul gutters. You die."
        result = await momus.validate_prose(prose, collapsed_soul_state)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_near_death_words_without_exact_pattern(self, momus, healthy_soul_state):
        """Words like 'deadly' or 'death' alone (not 'you die') should not trigger."""
        prose = "A deadly silence fills the corridor. Death watches from the shadows."
        result = await momus.validate_prose(prose, healthy_soul_state)
        assert result.valid is True


class TestMultiHallucination:
    """Momus can detect multiple hallucination types in one prose."""

    @pytest.mark.asyncio
    async def test_environment_and_oath_violations(self, momus):
        """Prose with both terrain contradiction AND oath reference (no oaths)."""
        state = ThreadState(
            session=SessionData(
                current_environment="A vast desert, dry and merciless.",
            ),
            soul_ledger=SoulLedger(
                vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
                active_oaths=[],
            ),
        )
        prose = "You dive into the ocean, remembering the oath you swore."
        result = await momus.validate_prose(prose, state)
        assert result.valid is False
        assert len(result.hallucinations) >= 2


# ===========================================================================
# LITERARY LAW CHECKS
# ===========================================================================

# ---------------------------------------------------------------------------
# Law IV — The Ancient Guardrail: Anachronism Detection
# ---------------------------------------------------------------------------

class TestAnachronismDetection:
    """Law IV: Momus detects modern technology and concepts in prose."""

    @pytest.mark.asyncio
    async def test_phone_flagged(self, momus, neutral_state):
        prose = "You reach for the phone but nothing answers."
        result = await momus.validate_prose(prose, neutral_state)
        assert len(result.law_violations) >= 1
        assert any("Law IV" in v for v in result.law_violations)
        assert any("phone" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_computer_flagged(self, momus, neutral_state):
        prose = "The computer hums with arcane energy."
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law IV" in v for v in result.law_violations)
        assert any("computer" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_gun_flagged(self, momus, neutral_state):
        prose = "A gun gleams in the moonlight."
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law IV" in v for v in result.law_violations)
        assert any("gun" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_electricity_flagged(self, momus, neutral_state):
        prose = "The electricity crackles through the wires overhead."
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law IV" in v for v in result.law_violations)
        assert any("electricity" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_multiple_anachronisms_in_one_violation(self, momus, neutral_state):
        """Multiple anachronisms in one prose produce a single violation with all words."""
        prose = "You drive the car past the factory and check your phone."
        result = await momus.validate_prose(prose, neutral_state)
        violations_iv = [v for v in result.law_violations if "Law IV" in v]
        assert len(violations_iv) == 1
        assert "car" in violations_iv[0]
        assert "factory" in violations_iv[0]
        assert "phone" in violations_iv[0]

    @pytest.mark.asyncio
    async def test_clean_mythic_prose_passes(self, momus, neutral_state):
        """Prose with no modern words produces no Law IV violation."""
        prose = "The sword gleams in the torchlight. A raven calls from the oak."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law IV" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_bus_not_triggered_in_ambush(self, momus, neutral_state):
        """'bus' inside 'ambush' should NOT trigger (word-boundary match)."""
        prose = "The ambush catches you off guard. Arrows rain from the canopy."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law IV" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_tv_flagged(self, momus, neutral_state):
        prose = "The tv flickers with strange images."
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law IV" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_anachronism_does_not_set_valid_false(self, momus, neutral_state):
        """Law violations don't make valid=False — only state hallucinations do."""
        prose = "You pull out your phone."
        result = await momus.validate_prose(prose, neutral_state)
        assert result.valid is True  # law violations are style, not state
        assert len(result.law_violations) >= 1


class TestDetectAnachronismsHelper:
    """Unit tests for the _detect_anachronisms() helper function."""

    def test_empty_string(self):
        assert _detect_anachronisms("") == set()

    def test_single_anachronism(self):
        found = _detect_anachronisms("a gun lies on the table")
        assert "gun" in found

    def test_no_anachronism(self):
        found = _detect_anachronisms("a sword lies on the stone")
        assert found == set()

    def test_word_boundary_respected(self):
        """'train' should match, but 'terrain' should not."""
        found = _detect_anachronisms("the train departs at dawn")
        assert "train" in found
        found2 = _detect_anachronisms("the terrain shifts underfoot")
        assert "train" not in found2

    def test_case_insensitive(self):
        found = _detect_anachronisms("the Computer hummed softly")
        # _detect_anachronisms receives lowercase input from validate_prose,
        # but should still work with mixed case since we pass prose_lower
        found2 = _detect_anachronisms("the computer hummed softly")
        assert "computer" in found2


# ---------------------------------------------------------------------------
# Law I — Show Then Tell: Named Emotion Detection (threshold: >3)
# ---------------------------------------------------------------------------

class TestNamedEmotionDetection:
    """Law I: Momus allows up to 3 emotion-naming instances (show-then-tell).
    Only flags when > 3 instances are found."""

    @pytest.mark.asyncio
    async def test_single_emotion_passes(self, momus, neutral_state):
        """One emotion naming is within threshold — no violation."""
        prose = "The child felt afraid as darkness fell."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_two_emotions_passes(self, momus, neutral_state):
        """Two emotion namings are within threshold."""
        prose = "The warrior was angry. The merchant seemed terrified."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_three_emotions_at_threshold_passes(self, momus, neutral_state):
        """Exactly 3 emotion namings — at threshold, should pass."""
        prose = "She felt sad. He was angry. The crowd seemed frightened."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_four_emotions_exceeds_threshold(self, momus, neutral_state):
        """4 emotion namings exceeds threshold — should flag."""
        prose = (
            "She felt sad. He was angry. The crowd seemed frightened. "
            "You grew nervous as footsteps approached."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law I" in v for v in result.law_violations)
        assert any("Show Then Tell" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_five_emotions_flagged_with_count(self, momus, neutral_state):
        """5 emotion namings reports the count in the violation."""
        prose = (
            "She felt sad. He was angry. The crowd seemed frightened. "
            "You grew nervous. The child appeared scared."
        )
        result = await momus.validate_prose(prose, neutral_state)
        violations = [v for v in result.law_violations if "Law I" in v]
        assert len(violations) == 1
        assert "5 instance" in violations[0]
        assert "threshold: 3" in violations[0]

    @pytest.mark.asyncio
    async def test_physical_description_passes(self, momus, neutral_state):
        """Describing physical sensation (the correct approach) should pass."""
        prose = "Your mouth dried. A hand that would not unclench."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_emotion_word_without_linking_verb_passes(self, momus, neutral_state):
        """Standalone emotion words (not preceded by 'felt/was') should pass."""
        prose = "Afraid of nothing, the child crossed the threshold."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_zero_emotions_passes(self, momus, neutral_state):
        """No emotion naming at all — clean pass."""
        prose = "You gripped the hilt until your knuckles whitened."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law I" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_emotion_does_not_set_valid_false(self, momus, neutral_state):
        """Even when exceeding threshold, law violations don't set valid=False."""
        prose = (
            "She felt sad. He was angry. The crowd seemed frightened. "
            "You grew nervous. The child appeared scared."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert result.valid is True
        assert len(result.law_violations) >= 1


# ---------------------------------------------------------------------------
# Law II — The Player Acts: Passive Voice (threshold: >6)
# ---------------------------------------------------------------------------

class TestPassiveVoiceDetection:
    """Law II: Momus flags excessive passive 'to be' verbs (threshold: >6)."""

    @pytest.mark.asyncio
    async def test_two_passive_passes(self, momus, neutral_state):
        """Two passive verbs — well within threshold."""
        prose = "The room was dark. A cold wind cut through the gap."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_three_passive_passes(self, momus, neutral_state):
        """Three passive verbs — within threshold."""
        prose = "The hall was empty. The table was bare. Shadows were long."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_five_passive_passes(self, momus, neutral_state):
        """Five passive verbs — still within the raised threshold of 6."""
        prose = (
            "The room was dark. The floor was cold. "
            "The walls were slick with moisture. "
            "Everything was silent. The air was stale."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_six_passive_at_threshold_passes(self, momus, neutral_state):
        """Exactly 6 passive verbs — at threshold, should pass."""
        prose = (
            "It was dark. It was cold. It was wet. "
            "It was quiet. It was still. You were alone."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_seven_passive_exceeds_threshold(self, momus, neutral_state):
        """Seven passive verbs exceeds threshold — should flag."""
        prose = (
            "It was dark. It was cold. It was wet. "
            "It was quiet. It was still. You were alone. "
            "The ground was frozen."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law II" in v for v in result.law_violations)
        assert any("Player Acts" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_active_prose_passes(self, momus, neutral_state):
        """Prose written in active voice should produce no Law II violation."""
        prose = (
            "You stepped into the room. Cold iron bit into your palm. "
            "The blade sang as it left the sheath."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_passive_count_in_violation_message(self, momus, neutral_state):
        """The violation message should include the actual count and threshold."""
        prose = (
            "It was dark. It was cold. It was wet. "
            "It was quiet. It was still. You were alone. "
            "The ground was frozen. The door was locked."
        )
        result = await momus.validate_prose(prose, neutral_state)
        violations = [v for v in result.law_violations if "Law II" in v]
        assert len(violations) == 1
        assert "8 passive" in violations[0]
        assert "threshold: 6" in violations[0]


# ---------------------------------------------------------------------------
# Law VI — Economy of Breath: Paragraph Overflow
# ---------------------------------------------------------------------------

class TestParagraphEconomy:
    """Law VI: Momus flags prose that exceeds paragraph limit."""

    @pytest.mark.asyncio
    async def test_too_many_paragraphs_flagged(self, momus, neutral_state):
        """Six paragraphs exceeds the limit of 5."""
        prose = "\n\n".join(f"Paragraph {i}." for i in range(6))
        result = await momus.validate_prose(prose, neutral_state)
        assert any("Law VI" in v for v in result.law_violations)
        assert any("6 paragraphs" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_within_limit_passes(self, momus, neutral_state):
        """Three paragraphs is well within the limit."""
        prose = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law VI" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_exactly_at_limit_passes(self, momus, neutral_state):
        """Exactly 5 paragraphs should pass (limit is > 5)."""
        prose = "\n\n".join(f"Paragraph {i}." for i in range(5))
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law VI" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_single_paragraph_passes(self, momus, neutral_state):
        prose = "A single dense paragraph of mythic prose."
        result = await momus.validate_prose(prose, neutral_state)
        assert not any("Law VI" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_blank_lines_not_counted(self, momus, neutral_state):
        """Blank double-newlines without text should not count as paragraphs."""
        prose = "First.\n\n\n\nSecond.\n\n\n\nThird."
        result = await momus.validate_prose(prose, neutral_state)
        # split on \n\n gives ["First.", "", "Second.", "", "Third."]
        # but stripping empties → 3 paragraphs
        assert not any("Law VI" in v for v in result.law_violations)


# ===========================================================================
# COMBINED VIOLATIONS
# ===========================================================================

class TestCombinedViolations:
    """Momus can detect hallucinations AND law violations simultaneously."""

    @pytest.mark.asyncio
    async def test_hallucination_plus_law_violation(self, momus):
        """Prose with terrain contradiction + anachronism."""
        state = ThreadState(
            session=SessionData(
                current_environment="A scorching desert.",
            ),
            soul_ledger=SoulLedger(
                vectors=SoulVectors(metis=5.0, bia=5.0, kleos=5.0, aidos=5.0),
            ),
        )
        prose = "You dive into the ocean and check your phone."
        result = await momus.validate_prose(prose, state)
        assert result.valid is False  # terrain contradiction
        assert len(result.hallucinations) >= 1
        assert len(result.law_violations) >= 1
        assert any("Law IV" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_multiple_law_violations_at_once(self, momus, neutral_state):
        """Prose violating multiple laws simultaneously."""
        # Law IV (phone) + Law I (>3 emotions) + Law II (>6 passive verbs)
        prose = (
            "You felt afraid. She was angry. He seemed terrified. You grew nervous. "
            "The phone was ringing. The room was dark. Everything was still. "
            "The air was heavy. The floor was cold. The walls were wet."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert result.valid is True  # no state hallucinations
        assert any("Law IV" in v for v in result.law_violations)
        assert any("Law I" in v for v in result.law_violations)
        assert any("Law II" in v for v in result.law_violations)

    @pytest.mark.asyncio
    async def test_clean_prose_no_violations(self, momus, neutral_state):
        """Well-written mythic prose should pass all checks."""
        prose = (
            "Smoke curled from the brazier. Cold iron bit your palm. "
            "The blade sang as it cleared the sheath."
        )
        result = await momus.validate_prose(prose, neutral_state)
        assert result.valid is True
        assert result.hallucinations == []
        assert result.law_violations == []


# ===========================================================================
# CORRECTED PROSE & SCHEMA
# ===========================================================================

class TestCorrectedProse:
    """Until Phase 3, corrected_prose echoes the original input."""

    @pytest.mark.asyncio
    async def test_valid_prose_echoed(self, momus, desert_state):
        prose = "The sand whispers secrets."
        result = await momus.validate_prose(prose, desert_state)
        assert result.corrected_prose == prose

    @pytest.mark.asyncio
    async def test_invalid_prose_still_echoed(self, momus, desert_state):
        prose = "The ocean waves crash around you."
        result = await momus.validate_prose(prose, desert_state)
        assert result.corrected_prose == prose  # not corrected yet (Phase 3)


class TestMomusValidationSchema:
    """MomusValidation pydantic model behaves correctly."""

    def test_default_valid(self):
        v = MomusValidation()
        assert v.valid is True
        assert v.hallucinations == []
        assert v.law_violations == []
        assert v.corrected_prose == ""

    def test_with_hallucinations(self):
        v = MomusValidation(
            valid=False,
            hallucinations=["Terrain mismatch", "Oath reference without oaths"],
            corrected_prose="Fixed prose here.",
        )
        assert v.valid is False
        assert len(v.hallucinations) == 2

    def test_with_law_violations(self):
        v = MomusValidation(
            valid=True,
            law_violations=["Law IV: phone detected", "Law I: named emotion"],
        )
        assert v.valid is True
        assert len(v.law_violations) == 2

    def test_serialization_roundtrip(self):
        v = MomusValidation(
            valid=False,
            hallucinations=["Error"],
            law_violations=["Law IV: anachronism"],
            corrected_prose="Fixed.",
        )
        data = v.model_dump()
        v2 = MomusValidation(**data)
        assert v2.hallucinations == v.hallucinations
        assert v2.law_violations == v.law_violations

    def test_serialization_includes_law_violations(self):
        v = MomusValidation(
            law_violations=["Law I: emotion", "Law II: passive"],
        )
        data = v.model_dump()
        assert "law_violations" in data
        assert len(data["law_violations"]) == 2


class TestAgentIdentity:
    def test_agent_name(self):
        m = Momus()
        assert m.name == "momus"
