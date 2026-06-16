"""Tests for the Oath Engine — deterministic oath detection and verification.

Extracted from TestDetectOath in test_lachesis.py (P1-002).
"""

from app.schemas.state import Oath, OathTerms, SoulLedger, ThreadState
from app.services.oath_engine import (
    detect_oath,
    oath_hypocrisy_score,
    verify_oaths,
)
from app.services.oath_parser import parse_oath_text


def _oath(oath_id: str, **term_kwargs) -> Oath:
    """An active oath with the given terms (None to omit terms entirely)."""
    terms = None if term_kwargs.pop("no_terms", False) else OathTerms(
        subject="Hero", **term_kwargs
    )
    return Oath(oath_id=oath_id, text="...", turn_sworn=2, terms=terms)


def _ledger(*oaths: Oath) -> ThreadState:
    return ThreadState(soul_ledger=SoulLedger(active_oaths=list(oaths)))


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

    # ── Empty / non-oath input ────────────────────────────────────────────

    def test_empty_string_returns_none(self):
        assert parse_oath_text("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_oath_text("   \t\n  ") is None

    def test_no_recognized_opening_keeps_whole_text_as_promised(self):
        # When no oath-opening phrase is present, the whole (stripped) text is the
        # promised action — the parser never drops the deed on the floor.
        terms = parse_oath_text("Glory shall be mine")
        assert terms is not None
        assert terms.promised_action == "Glory shall be mine"

    def test_subject_is_passed_through(self):
        terms = parse_oath_text("I swear to win", subject="Hero")
        assert terms is not None
        assert terms.subject == "Hero"

    # ── promised_action: every opening is stripped to the bare deed ───────

    def test_all_openings_strip_to_bare_promised_action(self):
        # Downstream verification compares deeds against the deed, not the vow
        # grammar, so every recognized opening must reduce to the action alone.
        cases = {
            "I swear to avenge my father": "avenge my father",
            "I promise to return home": "return home",
            "I vow to slay the beast": "slay the beast",
            "I pledge to serve the crown": "serve the crown",
            "My oath is to find her": "find her",
            "On my honor, I will act": "act",
            "On my blood, I will act": "act",
            "On my life, I will act": "act",
            "I will burn it all down": "burn it all down",
        }
        for text, expected in cases.items():
            terms = parse_oath_text(text)
            assert terms is not None, text
            assert terms.promised_action == expected, text

    # ── price: honor | blood | life, resolved in priority order ───────────

    def test_price_honor_blood_life(self):
        assert parse_oath_text("On my honor, I will act").price == "honor"
        assert parse_oath_text("On my blood, I will act").price == "blood"
        assert parse_oath_text("On my life, I will act").price == "life"

    def test_price_resolves_in_priority_order_when_multiple(self):
        # honor is tested before blood before life; the first hit wins, never both.
        terms = parse_oath_text("On my honor and on my blood, I will act")
        assert terms is not None
        assert terms.price == "honor"

    def test_no_price_when_unsworn(self):
        assert parse_oath_text("I swear to act").price is None

    # ── deadline ──────────────────────────────────────────────────────────

    def test_fixed_deadline_phrases(self):
        for phrase in (
            "before dawn", "before nightfall", "before sunrise",
            "before sunset", "tomorrow", "tonight",
        ):
            terms = parse_oath_text(f"I swear to act {phrase}")
            assert terms is not None, phrase
            assert terms.deadline == phrase, phrase

    def test_open_ended_deadline_by_and_until(self):
        assert parse_oath_text("I swear to act by the next moon").deadline == "by the next moon"
        assert parse_oath_text("I swear to act until the war ends").deadline == "until the war ends"

    def test_no_deadline_when_absent(self):
        assert parse_oath_text("I swear to act").deadline is None

    # ── protected_target: lookahead stops at the next clause ──────────────

    def test_protected_target_stops_before_deadline_clause(self):
        terms = parse_oath_text("On my honor, I will protect Sera before dawn")
        assert terms is not None
        assert terms.protected_target == "Sera"
        assert terms.deadline == "before dawn"

    def test_protected_target_stops_before_price_clause(self):
        terms = parse_oath_text("I swear to keep safe my brother on my life")
        assert terms is not None
        assert terms.protected_target == "my brother"
        assert terms.price == "life"

    def test_guard_and_defend_are_protect_verbs(self):
        assert parse_oath_text("On my life, I will guard the gate").protected_target == "the gate"
        assert (
            parse_oath_text("I swear to defend the orphans until the spring").protected_target
            == "the orphans"
        )

    # ── forbidden_action: never | not ─────────────────────────────────────

    def test_forbidden_action_from_never(self):
        terms = parse_oath_text("I vow to never betray the village")
        assert terms is not None
        assert terms.forbidden_action == "betray the village"

    def test_forbidden_action_from_not(self):
        terms = parse_oath_text("I will not abandon the keep")
        assert terms is not None
        assert terms.forbidden_action == "abandon the keep"

    # ── witness: a capitalized name after 'before' or 'to' ────────────────

    def test_witness_after_before_keyword(self):
        terms = parse_oath_text("I swear to kneel before Marn")
        assert terms is not None
        assert terms.witness == "Marn"

    def test_witness_after_to_keyword(self):
        terms = parse_oath_text("I promise to Sera that I will stay")
        assert terms is not None
        assert terms.witness == "Sera"

    def test_witness_requires_a_capitalized_name(self):
        # 'to protect' is lowercase — not a witness; the target extractor owns it.
        terms = parse_oath_text("I swear to protect the village")
        assert terms is not None
        assert terms.witness is None
        assert terms.protected_target == "the village"


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


class TestVerifyOathsEdges:
    """The death-critical break/skip branches the happy-path tests miss."""

    def test_forbidden_action_breaks_the_oath(self):
        # A "never X" oath is broken by doing X — the most direct path to
        # oath-break → Nemesis lethal → death. The deed verb AND its object are
        # present, so the break is real.
        state = _ledger(_oath("o1", forbidden_action="betray the village"))
        broken, fulfilled, transformed = verify_oaths(state, "I betray the village at dawn")
        assert broken == ["o1"]
        assert fulfilled == [] and transformed == []

    def test_forbidden_oath_survives_an_innocent_noun_share(self):
        # audit S2: the old matcher broke the oath on a SINGLE shared noun, so
        # merely being near the village wrongly routed the player to an inescapable
        # broken-oath doom. An action that does not commit the deed must NOT break.
        state = _ledger(_oath("o1", forbidden_action="betray the village"))
        broken, _, _ = verify_oaths(state, "I walk through the village peacefully")
        assert broken == []

    def test_forbidden_oath_survives_a_fulfilling_action(self):
        # Even PROTECTING the village (the opposite of betrayal) shares the noun
        # and used to break "never betray the village". It must not.
        state = _ledger(_oath("o2", forbidden_action="betray the village"))
        broken, _, _ = verify_oaths(state, "I protect the village from raiders")
        assert broken == []

    def test_forbidden_oath_breaks_on_the_actual_deed(self):
        # The deed verb plus an object token still breaks it — no regression in
        # catching a genuine violation.
        state = _ledger(_oath("o3", forbidden_action="betray the village"))
        broken, _, _ = verify_oaths(state, "I betray the village elders for coin")
        assert broken == ["o3"]

    def test_oath_with_no_terms_is_skipped_not_crashed(self):
        # An oath whose text parsed to no structured terms must be inert in
        # verification, never raise.
        state = _ledger(_oath("o2", no_terms=True))
        assert verify_oaths(state, "I attack someone") == ([], [], [])

    def test_inactive_oath_is_ignored(self):
        state = _ledger(_oath("o3", forbidden_action="betray the village"))
        state.soul_ledger.active_oaths[0].status = "broken"
        assert verify_oaths(state, "I betray the village") == ([], [], [])


class TestOathHypocrisyScore:
    """Hypocrisy is open mockery of an oath short of fully breaking it — it
    feeds Nemesis's punishment trigger, so its scoring must stay pinned."""

    def test_threatening_the_protected_target_scores(self):
        state = _ledger(_oath("o1", promised_action="protect Mara", protected_target="Mara"))
        assert oath_hypocrisy_score(state.soul_ledger.active_oaths, "I threaten Mara openly") == 1.0

    def test_looting_while_sworn_to_protect_scores_half(self):
        # promised "protect" + a plundering verb, with no protected_target hit.
        state = _ledger(_oath("o2", promised_action="protect the weak"))
        assert oath_hypocrisy_score(state.soul_ledger.active_oaths, "I steal from the poor") == 0.5

    def test_lying_while_sworn_to_truth_scores(self):
        state = _ledger(_oath("o3", promised_action="speak only the truth"))
        assert oath_hypocrisy_score(state.soul_ledger.active_oaths, "I lie to the magistrate") == 1.0

    def test_clean_action_scores_zero(self):
        state = _ledger(_oath("o4", promised_action="protect Mara", protected_target="Mara"))
        assert oath_hypocrisy_score(state.soul_ledger.active_oaths, "I tend the garden") == 0.0

    def test_inactive_or_termless_oaths_do_not_score(self):
        active_termless = _oath("o5", no_terms=True)
        inactive = _oath("o6", promised_action="speak the truth")
        inactive.status = "fulfilled"
        score = oath_hypocrisy_score([active_termless, inactive], "I lie and threaten everyone")
        assert score == 0.0
