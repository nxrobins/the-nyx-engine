"""Tests for the Oath Engine — deterministic oath detection service.

Extracted from TestDetectOath in test_lachesis.py (P1-002).
"""

from app.services.oath_engine import detect_oath


class TestDetectOath:
    """detect_oath() identifies oath-swearing patterns in player actions."""

    def test_i_swear(self):
        assert detect_oath("I swear to protect the innocent") is not None

    def test_i_promise(self):
        assert detect_oath("I promise to return") is not None

    def test_i_vow(self):
        assert detect_oath("I vow vengeance") is not None

    def test_on_my_honor(self):
        assert detect_oath("On my honor, I will succeed") is not None

    def test_on_my_blood(self):
        assert detect_oath("On my blood, I will not fail") is not None

    def test_on_my_life(self):
        assert detect_oath("On my life, I shall prevail") is not None

    def test_i_pledge(self):
        assert detect_oath("I pledge my sword to the cause") is not None

    def test_my_oath(self):
        assert detect_oath("My oath binds me to this path") is not None

    def test_no_oath(self):
        assert detect_oath("I attack the goblin") is None

    def test_case_insensitive(self):
        assert detect_oath("I SWEAR BY THE GODS") is not None

    def test_returns_trimmed_action(self):
        result = detect_oath("  I swear to avenge my father  ")
        assert result == "I swear to avenge my father"

    def test_normal_sentence_no_false_positive(self):
        assert detect_oath("I walk into the tavern") is None

    def test_partial_word_no_match(self):
        """'swearing' should not trigger — we match whole word 'swear'."""
        # "I swear" is a whole word match; "swearing" contains "swear" as substring
        # but \b ensures word boundary, so "swearing" would actually fail
        # Let's verify the regex boundary works correctly
        result = detect_oath("The merchant was swearing loudly")
        # "swearing" contains "swear" but \bswear\b won't match "swearing"
        # because the \b after 'swear' would need a word boundary
        # Actually \bi swear\b looks for "i swear" as a whole phrase
        assert result is None
