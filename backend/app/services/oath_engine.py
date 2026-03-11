"""Oath Engine — Deterministic Oath Detection Service.

Detects oath-swearing patterns in player actions via regex.
Zero LLM tokens — pure pattern matching.

Extracted from Lachesis (P1-002) to isolate deterministic logic
from LLM-dependent judgment. The Kernel is the sole consumer:
it calls detect_oath() during Step 3 of _resolve_turn().
"""

from __future__ import annotations

import re

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
