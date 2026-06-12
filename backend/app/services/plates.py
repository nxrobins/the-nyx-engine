"""The Plates — curated canon images, served under law (The Ink, Layer 1).

Plates are authored once per world (the Atelier), human-curated, and checked
in as cartridge sidecars under ``<worlds_dir>/art/{world_id}/``. This module
is the consumer-side gate. The laws, enforced at scan AND serve (INK-E3):

  - One filename law: ``_PLATE_RE`` (settlement | home | faction | npc_<slug>,
    png/webp). Anything else does not exist, at either door.
  - One size law: ``MAX_PLATE_BYTES`` (512 KB), checked before any read.
  - Containment: the resolved real path must live under the art root —
    a curator's stray symlink cannot escape (hygiene, not a security
    boundary against a hostile curator; see AG-Ink-1).
  - Never raise (INK-E2): every filesystem touch is wrapped; OSError on
    Windows (Defender, indexing locks) degrades to skip/404, never a 500.
  - No listing cache: the manifest re-scans every call, so the endpoint's
    Cache-Control: no-store stays truthful.

Fallback identity: missing dir, invalid world_id, or a scan that throws all
yield an empty manifest — the game renders exactly as it does without art.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from app.core.world_registry import _worlds_dir

logger = logging.getLogger("nyx.plates")

# The filename law. NPC stems are canon npc_ids verbatim (canon._slug emits
# [a-z0-9_], so ``npc_{slug}`` round-trips with zero frontend slugging).
_PLATE_RE = re.compile(r"^(settlement|home|faction|npc_[a-z0-9_]{1,80})\.(png|webp)$")

# Mirrors the registry's world_id law (cartridge.py pattern).
_WORLD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")

MAX_PLATE_BYTES = 524_288  # 512 KB — enforced at scan AND serve
MAX_DIR_ENTRIES = 64       # name-sorted; entries beyond are dropped, one WARNING

_MEDIA_TYPES = {".png": "image/png", ".webp": "image/webp"}


def _art_root(world_id: str) -> Path:
    """Art dir for a world — derived from the registry's dir resolution.

    No new setting (the registry's ``worlds_dir`` redirect isolates art in
    tests too); ``test_plates.py`` monkeypatches THIS function as the named
    seam when it wants a bare tmp_path.
    """
    return _worlds_dir() / "art" / world_id


def _contained(path: Path, root: Path) -> bool:
    """True iff path's real location is under root's real location."""
    try:
        real = os.path.realpath(path)
        real_root = os.path.realpath(root)
        return os.path.commonpath([real, real_root]) == real_root
    except (OSError, ValueError):
        return False


def plate_manifest(world_id: str) -> dict:
    """Scan a world's art dir. Returns {world_id, plates: {stem: url}, skipped}.

    Never raises. Re-scans every call (no listing cache). Skips are
    diagnosable: each carries a reason and logs a WARNING, so a mis-promoted
    file is visible instead of silently black.
    """
    plates: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    result = {"world_id": world_id, "plates": plates, "skipped": skipped}

    if not world_id or not _WORLD_ID_RE.fullmatch(world_id):
        return result

    root = _art_root(world_id)
    try:
        if not root.is_dir():
            return result
        entries = sorted(os.listdir(root))
    except OSError as exc:
        logger.warning(f"plates/{world_id}: cannot scan {root}: {exc}")
        return result

    if len(entries) > MAX_DIR_ENTRIES:
        logger.warning(
            f"plates/{world_id}: {len(entries)} entries, serving first {MAX_DIR_ENTRIES}"
        )
        entries = entries[:MAX_DIR_ENTRIES]

    for name in entries:
        try:
            if not _PLATE_RE.fullmatch(name):
                skipped.append({"file": name, "reason": "name does not match the plate law"})
                continue
            path = root / name
            if not path.is_file() or not _contained(path, root):
                skipped.append({"file": name, "reason": "not a contained regular file"})
                continue
            size = path.stat().st_size
            if size > MAX_PLATE_BYTES:
                skipped.append({
                    "file": name,
                    "reason": f"oversize ({size} B > {MAX_PLATE_BYTES}); convert to webp",
                })
                continue
            stem = name.rsplit(".", 1)[0]
            plates[stem] = f"/api/plates/{world_id}/{name}"
        except OSError as exc:  # INK-E2: one unreadable file never breaks the scan
            skipped.append({"file": name, "reason": f"unreadable: {exc}"})

    for entry in skipped:
        logger.warning(f"plates/{world_id}: skipped {entry['file']}: {entry['reason']}")
    return result


def resolve_plate(world_id: str, filename: str) -> tuple[Path | None, str, int]:
    """Serve-time gate (INK-E3) — re-applies every law before opening.

    Returns (path, media_type, 200) when lawful; (None, "", 404) for any
    name/containment failure; (None, "", 413) for oversize. Never raises.
    """
    if not world_id or not _WORLD_ID_RE.fullmatch(world_id):
        return None, "", 404
    if not filename or not _PLATE_RE.fullmatch(filename):
        return None, "", 404

    root = _art_root(world_id)
    path = root / filename
    try:
        if not path.is_file() or not _contained(path, root):
            return None, "", 404
        if path.stat().st_size > MAX_PLATE_BYTES:
            return None, "", 413
    except OSError as exc:
        logger.warning(f"plates/{world_id}/{filename}: {exc}")
        return None, "", 404

    media = _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return path, media, 200
