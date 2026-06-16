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


class TestProtectOathDefensiveActions:
    """A protect-oath must break only on a DIRECT attack on the target, never on
    a defensive act that names the target while harming something else.

    The forbidden-action branch was hardened for this exact false-positive class
    in audit S2; the protected_target branch is its symmetric twin. A false break
    here seals an UNESCAPABLE broken-oath doom (begin_doom escapable=False), so the
    player is killed two turns later for KEEPING the oath — the engine punishing
    fidelity. These pin the asymmetry closed.
    """

    @staticmethod
    def _protect(oath_id="o1"):
        return _ledger(_oath(oath_id, promised_action="protect Sera", protected_target="Sera"))

    def test_defending_the_target_does_not_break(self):
        # The blow lands on the bandit/dragon/wolves, not on Sera; the oath holds.
        for action in (
            "I strike the bandit threatening Sera",
            "I kill the dragon to save Sera",
            "I attack the wolves circling Sera to protect her",
        ):
            broken, _, _ = verify_oaths(self._protect(), action)
            assert broken == [], action

    def test_a_direct_attack_on_the_target_still_breaks(self):
        # Regression guard: the genuine betrayal must still seal the doom.
        for action in ("I attack Sera with my knife", "I strike Sera", "I kill Sera"):
            broken, _, _ = verify_oaths(self._protect(), action)
            assert broken == ["o1"], action

    def test_naming_the_target_without_a_harm_verb_does_not_break(self):
        broken, _, _ = verify_oaths(self._protect(), "I walk beside Sera through the market")
        assert broken == []

    def test_a_protective_verb_spares_the_oath(self):
        broken, _, _ = verify_oaths(self._protect(), "I guard Sera from the raiders")
        assert broken == []

    def test_a_far_off_harm_verb_does_not_reach_the_target(self):
        # The harm verb governs a different object several tokens away.
        broken, _, _ = verify_oaths(
            self._protect(), "I stab the cutpurse who once tried to rob Sera"
        )
        assert broken == []


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

    def test_striking_a_bystander_near_the_target_is_not_hypocrisy(self):
        # The protected target is named but the blow lands on someone else —
        # defending Mara is not mockery of the oath to protect her (mirrors the
        # protected_target object-binding fix in verify_oaths).
        state = _ledger(_oath("o7", promised_action="protect Mara", protected_target="Mara"))
        score = oath_hypocrisy_score(state.soul_ledger.active_oaths, "I strike the thug menacing Mara")
        assert score == 0.0

    def test_inactive_or_termless_oaths_do_not_score(self):
        active_termless = _oath("o5", no_terms=True)
        inactive = _oath("o6", promised_action="speak the truth")
        inactive.status = "fulfilled"
        score = oath_hypocrisy_score([active_termless, inactive], "I lie and threaten everyone")
        assert score == 0.0
