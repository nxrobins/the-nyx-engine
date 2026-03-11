"""Tests for the Epoch State Machine — controls UI mode + prose length per phase.

Phase 1 (turns 1-3):  buttons
Phase 2 (turns 4-6):  buttons
Phase 3 (turns 7-9):  buttons
Phase 4 (turns 10+):  open
"""

from app.core.kernel import _compute_epoch


class TestComputeEpoch:
    """Direct unit tests for the _compute_epoch function."""

    # Phase 1: turns 1-3
    def test_turn_1(self):
        phase, mode = _compute_epoch(1)
        assert phase == 1
        assert mode == "buttons"

    def test_turn_3(self):
        phase, mode = _compute_epoch(3)
        assert phase == 1
        assert mode == "buttons"

    # Phase 2: turns 4-6
    def test_turn_4(self):
        phase, mode = _compute_epoch(4)
        assert phase == 2
        assert mode == "buttons"

    def test_turn_6(self):
        phase, mode = _compute_epoch(6)
        assert phase == 2
        assert mode == "buttons"

    # Phase 3: turns 7-9
    def test_turn_7(self):
        phase, mode = _compute_epoch(7)
        assert phase == 3
        assert mode == "buttons"

    def test_turn_9(self):
        phase, mode = _compute_epoch(9)
        assert phase == 3
        assert mode == "buttons"

    # Phase 4: turns 10+
    def test_turn_10(self):
        phase, mode = _compute_epoch(10)
        assert phase == 4
        assert mode == "open"

    def test_turn_50(self):
        phase, mode = _compute_epoch(50)
        assert phase == 4
        assert mode == "open"

    def test_turn_100(self):
        phase, mode = _compute_epoch(100)
        assert phase == 4
        assert mode == "open"

    # Boundary tests
    def test_boundary_3_to_4(self):
        """Phase transition from 1→2 at turn 4."""
        p3, m3 = _compute_epoch(3)
        p4, m4 = _compute_epoch(4)
        assert p3 == 1
        assert p4 == 2
        assert m3 == m4 == "buttons"

    def test_boundary_6_to_7(self):
        """Phase transition from 2→3 at turn 7."""
        p6, _ = _compute_epoch(6)
        p7, _ = _compute_epoch(7)
        assert p6 == 2
        assert p7 == 3

    def test_boundary_9_to_10(self):
        """Critical phase transition from 3→4 at turn 10 — UI mode changes."""
        p9, m9 = _compute_epoch(9)
        p10, m10 = _compute_epoch(10)
        assert p9 == 3
        assert m9 == "buttons"
        assert p10 == 4
        assert m10 == "open"

    # Edge case
    def test_turn_0(self):
        """Turn 0 isn't a real game turn, but function should handle it."""
        phase, mode = _compute_epoch(0)
        # 0 ≤ 3 → Phase 1
        assert phase == 1
        assert mode == "buttons"
