"""Oath Parser — structured extraction from detected oath language."""

from __future__ import annotations

import re

from app.schemas.state import OathTerms

_PRICE_PATTERNS = [
    (re.compile(r"\bon my honor\b", re.IGNORECASE), "honor"),
    (re.compile(r"\bon my blood\b", re.IGNORECASE), "blood"),
    (re.compile(r"\bon my life\b", re.IGNORECASE), "life"),
]

_WITNESS_RE = re.compile(r"\b(before|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")
_DEADLINE_RE = re.compile(
    r"\b(before dawn|before nightfall|before sunrise|before sunset|tomorrow|tonight|by [^,.]+|until [^,.]+)\b",
    re.IGNORECASE,
)


def parse_oath_text(text: str, subject: str = "I") -> OathTerms | None:
    """Extract a structured oath contract from raw oath text."""
    stripped = text.strip()
    if not stripped:
        return None

    lowered = stripped.lower()
    promised_action = stripped
    for phrase in (
        "i swear to",
        "i promise to",
        "i vow to",
        "i pledge to",
        "my oath is to",
        "on my honor, i will",
        "on my blood, i will",
        "on my life, i will",
        "i will",
    ):
        if phrase in lowered:
            start = lowered.find(phrase) + len(phrase)
            promised_action = stripped[start:].strip(" ,.")
            break

    protected_target: str | None = None
    protect_match = re.search(
        r"\b(?:protect|defend|keep safe|guard|save)\s+"
        r"(.+?)"
        r"(?=\s+(?:before|by|until|tonight|tomorrow|on my honor|on my blood|on my life)\b|[,.!?]|$)",
        stripped,
        re.IGNORECASE,
    )
    if protect_match:
        protected_target = protect_match.group(1).strip()

    forbidden_action: str | None = None
    forbidden_match = re.search(
        r"\b(?:never|not)\s+([a-z][^,.]+)",
        stripped,
        re.IGNORECASE,
    )
    if forbidden_match:
        forbidden_action = forbidden_match.group(1).strip()

    deadline_match = _DEADLINE_RE.search(stripped)
    witness_match = _WITNESS_RE.search(stripped)

    price: str | None = None
    for pattern, label in _PRICE_PATTERNS:
        if pattern.search(stripped):
            price = label
            break

    return OathTerms(
        subject=subject,
        promised_action=promised_action or stripped,
        protected_target=protected_target,
        forbidden_action=forbidden_action,
        deadline=deadline_match.group(1) if deadline_match else None,
        witness=witness_match.group(2) if witness_match else None,
        price=price,
    )
