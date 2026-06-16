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


def _target_harmed(action: str, target: str) -> bool:
    lowered = _normalize(action)
    if _normalize(target) not in lowered:
        return False
    return any(
        verb in lowered.split()
        for verb in ("attack", "stab", "kill", "strike", "hurt", "betray", "abandon")
    )


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

        if terms.protected_target and _normalize(terms.protected_target) in lowered:
            if any(word in lowered.split() for word in ("threaten", "strike", "mock", "abandon")):
                score += 1.0
        if "protect" in _normalize(terms.promised_action) and any(
            word in lowered.split() for word in ("loot", "steal", "burn")
        ):
            score += 0.5
        if "truth" in _normalize(terms.promised_action) and "lie" in lowered.split():
            score += 1.0
    return score
