"""The Vigil — Player Safety (crisis-routing + privacy floor).

ONE canonical flagged set, owned here, used by BOTH the care channel
(`detect_crisis`, surfaced as the crisis interstitial) AND the kernel's
durable-store redaction (`flags_sensitive_input`, an alias of `is_flagged`).
Care and privacy can therefore never desync (SAFE-C1/C7): anything that shows
the crisis card is also kept out of the log, the unauthenticated DB, and the
vector store.

The flagged set is the real-world-framed subset of `atropos_death_keywords`
(`REAL_WORLD_ATROPOS_PHRASES`) UNION a first-person ideation pattern set. The
purely-poetic game phrases ("embrace the void", "welcome oblivion") still
trigger the in-fiction death in `atropos.py` (unchanged — that is the fiction),
but they are NOT genuine real-world disclosures, so they neither raise the care
card nor are treated as sensitive. The discriminator is the real-world referent.

GATING: `detect_crisis` + redaction run on EVERY turn regardless of
`settings.welfare_copy_reviewed` (SAFE-C2). ONLY the rendered card / consent
copy is gated — that gate lives at the route's two display sites, never here.

DRAFT — the ideation patterns and `CRISIS_RESOURCES` copy are a high-precision,
LOW-RECALL floor pending human (ideally clinical) review before
`welfare_copy_reviewed` is flipped. The always-on client help link (SAFE-C8) is
the honest backstop for everything the regex misses; no copy claims completeness.
"""

from __future__ import annotations

import json
import re

from app.core.config import settings
from app.schemas.welfare import CrisisSignal

# What replaces a flagged action everywhere it would otherwise be persisted.
REDACTION_TOKEN = "[redacted: welfare-flagged input]"

# Cap the scanned action (the phrases are short; a megabyte action can't DoS
# the regex, and a leading phrase can't hide past 4096 chars).
_SCAN_CAP = 4096

# The real-world-framed subset of atropos_death_keywords. A merge-blocking test
# asserts each of these is in settings.atropos_death_keywords (the superset
# invariant): any real-world death phrase MUST also route to care.
REAL_WORLD_ATROPOS_PHRASES: tuple[str, ...] = (
    "drink the poison",
    "jump off",
    "end my thread",
    "cut my own thread",
    "give up completely",
)

# First-person ideation. DRAFT — pending human/clinical review (AG-C5).
_IDEATION_SOURCE: tuple[str, ...] = (
    r"\bi\s+(?:want|wanna|need|wish|am going|'?m going|plan|have|hope)\s+to\s+"
    r"(?:kill|hurt|harm|end)\s+(?:myself|my\s?self|it\s+all|my\s+life)\b",
    r"\bi\s+(?:want|wanna|wish)\s+to\s+die\b",
    r"\bkill\s+myself\b",
    r"\b(?:hurt|harm)\s+myself\b",
    r"\bend\s+(?:it\s+all|my\s+life)\b",
    r"\bi\s+(?:can'?t|cannot)\s+(?:go\s+on|do\s+this(?:\s+anymore)?|"
    r"take\s+(?:it|this)\s+anymore|live\s+like\s+this)\b",
    r"\bi\s+do(?:n'?t|\s+not)\s+want\s+to\s+(?:be\s+here|live)(?:\s+anymore)?\b",
    r"\bi'?m\s+going\s+to\s+end\s+(?:it|my\s+life|myself)\b",
    r"\bsuicid(?:e|al)\b",
)
_IDEATION_PATTERNS: tuple[re.Pattern, ...] = tuple(re.compile(p, re.I) for p in _IDEATION_SOURCE)


def _canonical(action: str) -> str:
    return re.sub(r"\s+", " ", (action or "").lower()).strip()[:_SCAN_CAP]


def detect_crisis(action: str) -> CrisisSignal:
    """The ONE canonical detector. Pure, deterministic, keyless, never raises.

    Fail-SAFE: on ANY internal error, returns flagged=True (show help + redact)
    — never silently 'not flagged'. Returns only a boolean + coarse class,
    never the matched substring (privacy).
    """
    try:
        canon = _canonical(action)
        if any(phrase in canon for phrase in REAL_WORLD_ATROPOS_PHRASES):
            return CrisisSignal(flagged=True, pattern_class="self_destruct")
        if any(rx.search(canon) for rx in _IDEATION_PATTERNS):
            return CrisisSignal(flagged=True, pattern_class="ideation")
        return CrisisSignal(flagged=False, pattern_class="")
    except Exception:
        return CrisisSignal(flagged=True, pattern_class="ideation")


def is_flagged(action: str) -> bool:
    """Canonical predicate — drives BOTH care and redaction (SAFE-C7)."""
    return detect_crisis(action).flagged


# The kernel's Phase-1 redaction imports this name; aliasing it to the canonical
# detector makes the kernel adopt the unified set with no kernel edit, so the
# redacted set and the crisis-flagged set are physically identical.
flags_sensitive_input = is_flagged


# ---------------------------------------------------------------------------
# Crisis resources — static, server-owned DRAFT copy (gated by the route).
# DRAFT — pending human/clinical review before welfare_copy_reviewed is flipped.
# ---------------------------------------------------------------------------

CRISIS_RESOURCES: dict = {
    "title": "You don't have to face this alone",
    "body": (
        "If you're thinking about harming yourself or ending your life, please "
        "reach out — you deserve to talk to someone trained to help, right now."
    ),
    "resources": [
        {
            "label": "988 Suicide & Crisis Lifeline (US)",
            "detail": "Call or text 988, any time, day or night — or chat at 988lifeline.org.",
        },
        {
            "label": "Find a helpline anywhere",
            "detail": "findahelpline.com lists free, confidential support lines by country.",
        },
    ],
    "disclaimer": (
        "This is a game. These are real, independent services — the game does not "
        "counsel you, monitor you, or follow up. Please reach out to them directly."
    ),
    "draft": True,  # unreviewed; see backend/SAFETY.md
}


def _assert_resources_complete() -> None:
    """Import-time guard (SAFE-C5 / matrix): the server REFUSES to start with
    crisis copy that lacks a real lifeline, the international pointer, or a
    disclaimer — never serve a blank or half-broken card."""
    blob = json.dumps(CRISIS_RESOURCES)
    if "988" not in blob:
        raise RuntimeError("CRISIS_RESOURCES is missing the 988 lifeline reference")
    if "findahelpline.com" not in blob:
        raise RuntimeError("CRISIS_RESOURCES is missing the international (findahelpline.com) pointer")
    if not str(CRISIS_RESOURCES.get("disclaimer", "")).strip():
        raise RuntimeError("CRISIS_RESOURCES is missing the disclaimer")
    if len(blob.encode("utf-8")) > 2048:
        raise RuntimeError("CRISIS_RESOURCES exceeds the 2 KB payload cap")


_assert_resources_complete()
