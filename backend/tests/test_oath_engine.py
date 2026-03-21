"""Tests for the Oath Engine — deterministic oath detection and verification.

Extracted from TestDetectOath in test_lachesis.py (P1-002).
"""

from app.schemas.state import Oath, OathTerms, SoulLedger, ThreadState
from app.services.oath_engine import detect_oath, verify_oaths
from app.services.oath_parser import parse_oath_text


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


class TestParseOathText:
    """Structured oath terms are extracted for later verification."""

    def test_extracts_protected_target_and_price(self):
        terms = parse_oath_text("On my honor, I swear to protect Sera before dawn")
        assert terms is not None
        assert terms.protected_target == "Sera"
        assert terms.price == "honor"
        assert terms.deadline == "before dawn"

    def test_extracts_forbidden_action(self):
        terms = parse_oath_text("I vow to never betray the village")
        assert terms is not None
        assert terms.forbidden_action is not None
        assert "betray the village" in terms.forbidden_action.lower()


class TestVerifyOaths:
    """Active oaths can be broken, fulfilled, or transformed."""

    def test_protect_oath_breaks_when_target_is_attacked(self):
        state = ThreadState(
            soul_ledger=SoulLedger(
                active_oaths=[
                    Oath(
                        oath_id="oath_1",
                        text="I swear to protect Sera.",
                        turn_sworn=2,
                        terms=OathTerms(
                            subject="Hero",
                            promised_action="protect Sera",
                            protected_target="Sera",
                            price="honor",
                        ),
                    )
                ]
            )
        )

        broken, fulfilled, transformed = verify_oaths(state, "I attack Sera with my knife")
        assert broken == ["oath_1"]
        assert fulfilled == []
        assert transformed == []

    def test_promised_action_can_be_fulfilled(self):
        state = ThreadState(
            soul_ledger=SoulLedger(
                active_oaths=[
                    Oath(
                        oath_id="oath_2",
                        text="I promise to return the stolen coin.",
                        turn_sworn=2,
                        terms=OathTerms(
                            subject="Hero",
                            promised_action="return the stolen coin",
                        ),
                    )
                ]
            )
        )

        broken, fulfilled, transformed = verify_oaths(state, "I return the stolen coin to the widow")
        assert broken == []
        assert fulfilled == ["oath_2"]
        assert transformed == []

    def test_oath_can_be_transformed(self):
        state = ThreadState(
            soul_ledger=SoulLedger(
                active_oaths=[
                    Oath(
                        oath_id="oath_3",
                        text="I swear to serve the king.",
                        turn_sworn=2,
                        terms=OathTerms(
                            subject="Hero",
                            promised_action="serve the king",
                        ),
                    )
                ]
            )
        )

        broken, fulfilled, transformed = verify_oaths(state, "I renounce my oath before the court")
        assert broken == []
        assert fulfilled == []
        assert transformed == ["oath_3"]
