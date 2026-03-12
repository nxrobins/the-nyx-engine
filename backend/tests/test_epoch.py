"""Tests for _get_turn_metadata — Sprint 8: The Director.

Replaces TestComputeEpoch with comprehensive tests for:
- Deterministic age pinning per turn
- Phase mapping (1-4)
- Beat structure (SETUP / COMPLICATION / RESOLUTION / OPEN)
- UI mode (buttons / open)
- Authored vignette directives
- Boundary transitions
"""

from app.core.kernel import _get_turn_metadata


class TestPhaseMapping:
    """Phase assignment: turns 1-3→1, 4-6→2, 7-9→3, 10+→4."""

    def test_turns_1_to_3_are_phase_1(self):
        for t in (1, 2, 3):
            phase, *_ = _get_turn_metadata(t)
            assert phase == 1, f"Turn {t} should be phase 1"

    def test_turns_4_to_6_are_phase_2(self):
        for t in (4, 5, 6):
            phase, *_ = _get_turn_metadata(t)
            assert phase == 2, f"Turn {t} should be phase 2"

    def test_turns_7_to_9_are_phase_3(self):
        for t in (7, 8, 9):
            phase, *_ = _get_turn_metadata(t)
            assert phase == 3, f"Turn {t} should be phase 3"

    def test_turn_10_is_phase_4(self):
        phase, *_ = _get_turn_metadata(10)
        assert phase == 4

    def test_turn_50_is_phase_4(self):
        phase, *_ = _get_turn_metadata(50)
        assert phase == 4

    def test_turn_100_is_phase_4(self):
        phase, *_ = _get_turn_metadata(100)
        assert phase == 4


class TestAgePinning:
    """Deterministic age per turn — no drift within epochs."""

    def test_turn_1_age_3(self):
        _, age, *_ = _get_turn_metadata(1)
        assert age == 3

    def test_turn_2_age_4(self):
        _, age, *_ = _get_turn_metadata(2)
        assert age == 4

    def test_turn_3_age_5(self):
        _, age, *_ = _get_turn_metadata(3)
        assert age == 5

    def test_turn_4_age_7(self):
        _, age, *_ = _get_turn_metadata(4)
        assert age == 7

    def test_turn_5_age_8(self):
        _, age, *_ = _get_turn_metadata(5)
        assert age == 8

    def test_turn_6_age_10(self):
        _, age, *_ = _get_turn_metadata(6)
        assert age == 10

    def test_turn_7_age_12(self):
        _, age, *_ = _get_turn_metadata(7)
        assert age == 12

    def test_turn_8_age_14(self):
        _, age, *_ = _get_turn_metadata(8)
        assert age == 14

    def test_turn_9_age_17(self):
        _, age, *_ = _get_turn_metadata(9)
        assert age == 17

    def test_turn_10_age_18(self):
        _, age, *_ = _get_turn_metadata(10)
        assert age == 18

    def test_turn_12_age_20(self):
        _, age, *_ = _get_turn_metadata(12)
        assert age == 20

    def test_turn_30_age_38(self):
        _, age, *_ = _get_turn_metadata(30)
        assert age == 38


class TestUIMode:
    """Turns 1-9 → buttons, turns 10+ → open."""

    def test_buttons_phase_1(self):
        _, _, ui_mode, *_ = _get_turn_metadata(1)
        assert ui_mode == "buttons"

    def test_buttons_phase_2(self):
        _, _, ui_mode, *_ = _get_turn_metadata(5)
        assert ui_mode == "buttons"

    def test_buttons_phase_3(self):
        _, _, ui_mode, *_ = _get_turn_metadata(9)
        assert ui_mode == "buttons"

    def test_open_phase_4(self):
        _, _, ui_mode, *_ = _get_turn_metadata(10)
        assert ui_mode == "open"

    def test_open_deep_phase_4(self):
        _, _, ui_mode, *_ = _get_turn_metadata(50)
        assert ui_mode == "open"


class TestBeatStructure:
    """3-act structure per epoch: SETUP → COMPLICATION → RESOLUTION."""

    # Epoch 1
    def test_turn_1_setup(self):
        *_, beat, _ = _get_turn_metadata(1)
        assert beat == "SETUP"

    def test_turn_2_complication(self):
        *_, beat, _ = _get_turn_metadata(2)
        assert beat == "COMPLICATION"

    def test_turn_3_resolution(self):
        *_, beat, _ = _get_turn_metadata(3)
        assert beat == "RESOLUTION"

    # Epoch 2
    def test_turn_4_setup(self):
        *_, beat, _ = _get_turn_metadata(4)
        assert beat == "SETUP"

    def test_turn_5_complication(self):
        *_, beat, _ = _get_turn_metadata(5)
        assert beat == "COMPLICATION"

    def test_turn_6_resolution(self):
        *_, beat, _ = _get_turn_metadata(6)
        assert beat == "RESOLUTION"

    # Epoch 3
    def test_turn_7_setup(self):
        *_, beat, _ = _get_turn_metadata(7)
        assert beat == "SETUP"

    def test_turn_8_complication(self):
        *_, beat, _ = _get_turn_metadata(8)
        assert beat == "COMPLICATION"

    def test_turn_9_resolution(self):
        *_, beat, _ = _get_turn_metadata(9)
        assert beat == "RESOLUTION"

    # Phase 4: no beats
    def test_turn_10_open(self):
        *_, beat, _ = _get_turn_metadata(10)
        assert beat == "OPEN"

    def test_turn_20_open(self):
        *_, beat, _ = _get_turn_metadata(20)
        assert beat == "OPEN"


class TestVignetteDirectives:
    """Sprint 10: Scene isolation + physical grounding directives."""

    def test_all_beats_start_with_new_scene(self):
        """Every childhood beat starts with 'NEW SCENE.'"""
        for t in range(1, 10):
            *_, directive = _get_turn_metadata(t)
            assert "NEW SCENE" in directive, f"Turn {t} missing 'NEW SCENE': {directive[:60]}"

    def test_complication_beats_reference_time_passed(self):
        """COMPLICATION beats (2, 5, 8) mention time passing or previous scene."""
        for t in (2, 5, 8):
            *_, directive = _get_turn_metadata(t)
            has_time = "time has passed" in directive.lower() or "previous scene" in directive.lower()
            assert has_time, f"Turn {t} COMPLICATION missing time reference: {directive[:80]}"

    def test_resolution_beats_have_consequence(self):
        """RESOLUTION beats (3, 6, 9) mention immediate consequence."""
        for t in (3, 6, 9):
            *_, directive = _get_turn_metadata(t)
            has_consequence = "consequence" in directive.lower() or "door closes" in directive.lower()
            assert has_consequence, f"Turn {t} RESOLUTION missing consequence: {directive[:80]}"

    def test_multiple_beats_require_names(self):
        """Several beats mandate using character NAMES."""
        name_turns = 0
        for t in range(1, 10):
            *_, directive = _get_turn_metadata(t)
            if "NAME" in directive:
                name_turns += 1
        assert name_turns >= 3, f"Only {name_turns} beats mention NAMES"

    def test_dialogue_in_complication_beats(self):
        """At least some beats mandate DIALOGUE."""
        dialogue_turns = 0
        for t in range(1, 10):
            *_, directive = _get_turn_metadata(t)
            if "DIALOGUE" in directive:
                dialogue_turns += 1
        assert dialogue_turns >= 2, f"Only {dialogue_turns} beats mention DIALOGUE"

    def test_turn_1_home_and_parent(self):
        *_, directive = _get_turn_metadata(1)
        assert "home" in directive.lower() or "parent" in directive.lower()

    def test_turn_4_wider_world(self):
        *_, directive = _get_turn_metadata(4)
        assert "wider world" in directive.lower()

    def test_turn_9_door_or_adulthood(self):
        *_, directive = _get_turn_metadata(9)
        assert "door" in directive.lower() or "adulthood" in directive.lower()

    def test_phase_4_no_directive(self):
        *_, directive = _get_turn_metadata(10)
        assert directive == ""

    def test_phase_4_deep_no_directive(self):
        *_, directive = _get_turn_metadata(50)
        assert directive == ""

    def test_all_childhood_turns_have_directives(self):
        for t in range(1, 10):
            *_, directive = _get_turn_metadata(t)
            assert len(directive) > 20, f"Turn {t} directive too short: {directive!r}"


class TestBoundaryTransitions:
    """Phase boundaries and epoch transitions."""

    def test_phase_1_to_2(self):
        p3, *_ = _get_turn_metadata(3)
        p4, *_ = _get_turn_metadata(4)
        assert p3 == 1
        assert p4 == 2

    def test_phase_2_to_3(self):
        p6, *_ = _get_turn_metadata(6)
        p7, *_ = _get_turn_metadata(7)
        assert p6 == 2
        assert p7 == 3

    def test_phase_3_to_4(self):
        p9, _, m9, *_ = _get_turn_metadata(9)
        p10, _, m10, *_ = _get_turn_metadata(10)
        assert p9 == 3
        assert m9 == "buttons"
        assert p10 == 4
        assert m10 == "open"

    def test_age_jump_epoch_1_to_2(self):
        """Age 5 → 7: two years pass between epochs."""
        _, a3, *_ = _get_turn_metadata(3)
        _, a4, *_ = _get_turn_metadata(4)
        assert a3 == 5
        assert a4 == 7

    def test_age_jump_epoch_2_to_3(self):
        """Age 10 → 12: two years pass between epochs."""
        _, a6, *_ = _get_turn_metadata(6)
        _, a7, *_ = _get_turn_metadata(7)
        assert a6 == 10
        assert a7 == 12

    def test_age_jump_epoch_3_to_4(self):
        """Age 17 → 18: one year pass into adulthood."""
        _, a9, *_ = _get_turn_metadata(9)
        _, a10, *_ = _get_turn_metadata(10)
        assert a9 == 17
        assert a10 == 18


class TestEdgeCases:
    """Edge cases and return type validation."""

    def test_turn_0(self):
        """Turn 0 (init) should handle gracefully — phase 1, age from map or default."""
        phase, age, ui_mode, beat, directive = _get_turn_metadata(0)
        assert phase == 1
        # Turn 0 not in _AGE_MAP → falls to default: 18 + (0 - 10) = 8
        # That's fine — turn 0 is the init turn, not a real game turn
        assert isinstance(age, int)

    def test_return_type_is_tuple_of_five(self):
        result = _get_turn_metadata(1)
        assert isinstance(result, tuple)
        assert len(result) == 5

    def test_negative_turn(self):
        """Negative turns shouldn't crash."""
        phase, age, ui_mode, beat, directive = _get_turn_metadata(-1)
        assert phase == 1  # -1 <= 3
        assert isinstance(age, int)
