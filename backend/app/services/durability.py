"""Durability helpers — mint resume tokens and serialize a life for snapshotting.

Part of THE THREAD PERSISTS (audit H4/H2). A living thread is snapshotted after
every committed turn so it survives restart / TTL eviction / refresh. This module
holds the pure, model-free pieces:

- the schema-version stamp (CF-5) and the size ceiling (CF-4),
- an opaque, unguessable resume token (SC-4),
- serialization of ThreadState + the Scribe's Chapter list (SC-1), size-capped.

The store layer (db/) does the monotonic upsert (SC-3/CF-2); the kernel calls
`serialize_snapshot` best-effort (CF-7 — a snapshot never fails a turn).
"""

from __future__ import annotations

import json
import logging
import secrets

logger = logging.getLogger("nyx.durability")

# Bump when a ThreadState change makes old snapshots unreadable. On load, a
# mismatch is discarded to a fresh session, never up-converted (CF-5, AG-5).
SNAPSHOT_SCHEMA_VERSION = 1

# CF-4: a snapshot larger than this is skipped (loudly), never truncated. The
# real states measured are ~9 KB at turn 3; 256 KB is a wide, dumb ceiling that a
# pathological life cannot silently blow past.
SNAPSHOT_MAX_BYTES = 256 * 1024


def mint_resume_token() -> str:
    """An opaque, ~256-bit, owner-bound-by-secrecy handle (SC-4/CF-1).

    Distinct from player_id, so a snapshot is reachable only by its holder — no
    player_id-keyed enumeration. Forward-compatible with HMAC-signing when the
    auth-doorkeeper lands (the shape does not change).
    """
    return secrets.token_urlsafe(32)


def serialize_snapshot(state, chapters) -> tuple[str, str] | None:
    """Serialize (ThreadState, list[Chapter]) → (state_json, chapters_json).

    Returns None (and logs ERROR) if the payload exceeds SNAPSHOT_MAX_BYTES —
    the caller then skips the snapshot; the turn still commits (CF-4/CF-7).
    """
    state_json = state.model_dump_json()
    chapters_json = json.dumps([c.model_dump(mode="json") for c in chapters])
    total = len(state_json.encode("utf-8")) + len(chapters_json.encode("utf-8"))
    if total > SNAPSHOT_MAX_BYTES:
        logger.error(
            "snapshot %d bytes exceeds the %d cap; skipping (durability degraded "
            "for this thread, the turn still commits)",
            total, SNAPSHOT_MAX_BYTES,
        )
        return None
    return state_json, chapters_json
