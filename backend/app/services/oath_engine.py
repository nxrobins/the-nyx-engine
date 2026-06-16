"""Oath Engine — Deterministic Oath Detection and Verification Service.

Detects oath-swearing patterns in player actions via regex.
Zero LLM tokens — pure pattern matching.

Extracted from Lachesis (P1-002) to isolate deterministic logic
from LLM-dependent judgment. The Kernel is the sole consumer:
it calls detect_oath() during Step 3 of _resolve_turn().
"""

from __future__ import annotations

import re

from app.schemas.state import Oath, ThreadState

# ---------------------------------------------------------------------------
# Oath Patterns
# ---------------------------------------------------------------------------

_OATH_PATTERNS = [
    re.compile(r"\bi swear\b", re.IGNORECASE),
    re.compile(r"\bi promise\b", re.IGNORECASE),
    re.compile(r"\bi vow\b", re.IGNORECASE),
    re.compile(r"\bon my honor\b", re.IGNORECASE),
    re.compile(r"\bon my blood\b", re.IGNORECASE),
    re.compile(r"\bon my life\b", re.IGNORECASE),
    re.compile(r"\bi pledge\b", re.IGNORECASE),
    re.compile(r"\bmy oath\b", re.IGNORECASE),
]


def detect_oath(action: str) -> str | None:
    """Check if the player's action contains an oath.

    Returns the trimmed action text if an oath pattern is found,
    or None if no oath is detected. The returned text becomes
    the Oath.text stored on ThreadState.

    This is a pure function with no side effects.
    """
    for pattern in _OATH_PATTERNS:
        if pattern.search(action):
            return action.strip()
    return None


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()


def _shares_terms(action: str, clause: str) -> bool:
    action_tokens = set(_normalize(action).split())
    clause_tokens = {
        token for token in _normalize(clause).split()
        if token not in {"i", "will", "to", "the", "a", "an", "my"}
    }
    return bool(action_tokens & clause_tokens)


# Harm verbs that can break a protect-oath, and protective verbs that signal the
# action GUARDS the target rather than harming it. A protect-oath breaks only when
# a harm verb directly governs the protected target as its object — never when the
# target is merely named while something else is struck. This mirrors the S2
# hardening of _does_forbidden: better to miss an oblique break than to route a
# defensive act ("strike the bandit threatening Sera") to a permanent broken-oath
# doom for protecting the very person the oath was sworn to protect.
_HARM_VERBS: frozenset[str] = frozenset(
    {"attack", "stab", "kill", "strike", "hurt", "betray", "abandon"}
)
_PROTECTIVE_VERBS: frozenset[str] = frozenset(
    {"protect", "defend", "save", "guard", "shield", "rescue"}
)
# Verbs that constitute openly mocking a protected target (hypocrisy, not a break).
_HYPOCRISY_VERBS: frozenset[str] = frozenset({"threaten", "strike", "mock", "abandon"})

# How many tokens after a verb the target may appear and still count as its object.
# "attack the gate" (distance 2) binds; "strike the bandit threatening Sera"
# (distance 4) does not — there the verb governs "bandit", not the bystander "Sera".
_TARGET_GOVERN_WINDOW = 3


def _verb_governs_target(
    tokens: list[str], target_tokens: list[str], verbs: frozenset[str]
) -> bool:
    """True when one of ``verbs`` directly governs the target.

    A target token must appear within a short window AFTER the verb — i.e. as the
    verb's object — so a bystander named elsewhere in the sentence is never
    mistaken for the victim.
    """
    for i, tok in enumerate(tokens):
        if tok in verbs:
            window = tokens[i + 1 : i + 1 + _TARGET_GOVERN_WINDOW]
            if any(tt in window for tt in target_tokens):
                return True
    return False


def _target_harmed(action: str, target: str) -> bool:
    """True only when the action attacks the protected target directly.

    Requires (1) the target to be named, (2) NO protective verb present — a
    defensive act guards the target and never breaks the oath — and (3) a harm
    verb to directly govern the target as its object. So "I strike the bandit
    threatening Sera" and "I kill the dragon to save Sera" keep the oath, while
    "I attack Sera" still breaks it.
    """
    tokens = _normalize(action).split()
    target_tokens = [t for t in _normalize(target).split() if t not in _OATH_STOPWORDS]
    if not target_tokens or not all(t in tokens for t in target_tokens):
        return False
    if any(v in tokens for v in _PROTECTIVE_VERBS):
        return False
    return _verb_governs_target(tokens, target_tokens, _HARM_VERBS)


# Action/harm verbs that can constitute "doing the forbidden thing". A forbidden
# clause like "betray the village" is BROKEN only when the action shares this
# deed verb AND an object token — mirroring _target_harmed (target name + harm
# verb). The old _shares_terms broke on a SINGLE shared noun, so "walk through
# the village" or even "protect the village" wrongly severed a "never betray the
# village" oath → an inescapable broken-oath doom. Better to miss an oblique
# break than to route an innocent act to a permanent death (audit S2).
_FORBIDDEN_VERBS: frozenset[str] = frozenset({
    "attack", "stab", "kill", "strike", "hurt", "harm", "betray", "abandon",
    "steal", "rob", "loot", "burn", "deceive", "lie", "break", "destroy",
    "poison", "murder", "slay", "raid", "sabotage",
})

_OATH_STOPWORDS: frozenset[str] = frozenset({
    "i", "will", "to", "the", "a", "an", "my", "of", "and", "from", "with",
    "at", "in", "on", "them", "it",
})


def _does_forbidden(action: str, forbidden_action: str) -> bool:
    """True only when the action actually COMMITS the forbidden deed.

    Requires the forbidden clause's deed verb AND (if it has any) one of its
    object tokens, so a benign action that merely shares a noun with the clause
    does NOT break the oath. Falls back to requiring the whole clause present
    when no deed verb is recognised — still far stricter than any-shared-token.
    """
    action_tokens = set(_normalize(action).split())
    clause_tokens = [
        t for t in _normalize(forbidden_action).split() if t not in _OATH_STOPWORDS
    ]
    if not clause_tokens:
        return False
    deed_verbs = [t for t in clause_tokens if t in _FORBIDDEN_VERBS]
    objects = [t for t in clause_tokens if t not in _FORBIDDEN_VERBS]
    if deed_verbs:
        verb_hit = any(v in action_tokens for v in deed_verbs)
        object_hit = not objects or any(o in action_tokens for o in objects)
        return verb_hit and object_hit
    # No recognised deed verb: require the full clause present (conservative).
    return all(t in action_tokens for t in clause_tokens)


def verify_oaths(state: ThreadState, action: str) -> tuple[list[str], list[str], list[str]]:
    """Compare an action against active oath terms.

    Returns (broken_ids, fulfilled_ids, transformed_ids).
    """
    broken_ids: list[str] = []
    fulfilled_ids: list[str] = []
    transformed_ids: list[str] = []
    lowered = _normalize(action)

    for oath in state.soul_ledger.active_oaths:
        if oath.status != "active":
            continue

        if "renounce" in lowered or "withdraw my oath" in lowered:
            transformed_ids.append(oath.oath_id)
            continue

        if oath.terms is None:
            continue

        if oath.terms.forbidden_action and _does_forbidden(action, oath.terms.forbidden_action):
            broken_ids.append(oath.oath_id)
            continue

        if oath.terms.protected_target and _target_harmed(action, oath.terms.protected_target):
            broken_ids.append(oath.oath_id)
            continue

        if oath.terms.promised_action and _shares_terms(action, oath.terms.promised_action):
            fulfilled_ids.append(oath.oath_id)

    return broken_ids, fulfilled_ids, transformed_ids


def oath_hypocrisy_score(oaths: list[Oath], action: str) -> float:
    """Estimate how openly the action mocks an active oath without fully breaking it."""
    lowered = _normalize(action)
    score = 0.0
    for oath in oaths:
        if oath.status != "active":
            continue
        terms = oath.terms
        if not terms:
            continue

        if terms.protected_target:
            tokens = lowered.split()
            target_tokens = [
                t for t in _normalize(terms.protected_target).split()
                if t not in _OATH_STOPWORDS
            ]
            # Same object-binding as _target_harmed: striking a bystander who
            # merely stands near the protected target is not mockery of the oath.
            if (
                target_tokens
                and all(t in tokens for t in target_tokens)
                and not any(v in tokens for v in _PROTECTIVE_VERBS)
                and _verb_governs_target(tokens, target_tokens, _HYPOCRISY_VERBS)
            ):
                score += 1.0
        if "protect" in _normalize(terms.promised_action) and any(
            word in lowered.split() for word in ("loot", "steal", "burn")
        ):
            score += 0.5
        if "truth" in _normalize(terms.promised_action) and "lie" in lowered.split():
            score += 1.0
    return score
