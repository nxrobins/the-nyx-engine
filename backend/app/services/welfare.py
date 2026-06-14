"""The Vigil — Player Safety, Phase 1 (the pure-engineering floor).

This module ships ONLY the privacy-redaction helper that keeps a player's typed
self-destruction framing out of durable, world-readable stores (logs, the
unauthenticated DB, the vector store). It couples to the EXISTING
``atropos_death_keywords`` — it authors NO new crisis-detection vocabulary.

DEFERRED to human + clinical review (NOT shipped here — see backend/SAFETY.md):
the consent / content-warning UI, crisis-resource copy (988 /
findahelpline.com), the ideation detection-pattern expansion, and the Aletheia
welfare classifier. Those carry real-world duty-of-care weight and must not be
authored or rendered live without human (and ideally clinical) sign-off; they
are gated behind ``settings.welfare_copy_reviewed``.

Phase 1 is pure engineering with no authored crisis content: input redaction
(privacy) + the self-destruction miracle-exemption (permanence, in resolver.py).
Both are deterministic and keyless — they protect the default public engine.
"""

from __future__ import annotations

from app.core.config import settings

# What replaces a flagged action everywhere it would otherwise be persisted.
REDACTION_TOKEN = "[redacted: welfare-flagged input]"


def flags_sensitive_input(action: str) -> bool:
    """True if the action contains a self-destruction framing.

    Reuses the existing atropos_death_keywords (the phrases the engine already
    treats as self-destruction) so NO new crisis vocabulary is authored here.
    Pure, deterministic, keyless — it works on the default keyless engine.
    """
    lowered = action.lower()
    return any(keyword in lowered for keyword in settings.atropos_death_keywords)
