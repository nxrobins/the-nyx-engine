"""The Atelier — authoring-time plate generation for world cartridges.

    python -m app.tools.atelier --world <world_id> [--only settlement,home] [--dry-run]

Generates the canonical image set for one world — settlement, home, faction,
one portrait per family NPC — from **cartridge facts only**: names, kinds,
conditions, traits. Nothing is invented; plates depict what the cartridge
declares (the anti-hallucination rule, applied to pixels). The sumi-e style
wrap comes from ``generate_image`` exactly as it does for milestones.

Plan/execute split:
  - ``plan_plates(cartridge)`` is pure and deterministic — the tested
    producer/consumer contract (every filename matches ``plates._PLATE_RE``;
    NPC stems are canon npc_ids verbatim).
  - ``execute(jobs)`` calls BFL with ``output_format="png"`` and downloads
    the result bytes IMMEDIATELY (BFL URLs expire), writing atomically
    (temp + os.replace) to STAGING ONLY: ``worlds/art/_staging/{world_id}/``.
    Promotion into the live ``worlds/art/{world_id}/`` is the human curation
    step, by design — the Atelier proposes, the curator canonizes.

The dumb limits: ≤ 20 jobs/world (refuse, exit 2, before any API call);
30 s download timeout; streamed read aborts at 8 MB; a download-only failure
never re-pays for generation (≤ 2 same-URL retries, then the job fails);
any failed job → exit 1. ``--dry-run`` prints the plan and calls nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.world_registry import _worlds_dir
from app.schemas.cartridge import WorldCartridge, slugify
from app.services.bfl import generate_image

logger = logging.getLogger("nyx.atelier")

MAX_JOBS = 20                       # 3 fixed + ≤12 family + headroom
DOWNLOAD_TIMEOUT = 30.0             # seconds, per attempt
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024  # staging cap (raw pre-curation PNG)
DOWNLOAD_RETRIES = 2                # same-URL retries; generation is never re-paid
SERVE_CAP_BYTES = 524_288           # the live 512 KB law — warn the curator early


@dataclass(frozen=True)
class PlateJob:
    """One plate to paint: a lawful filename and a canon-fact prompt."""
    filename: str
    prompt: str


# ---------------------------------------------------------------------------
# Plan (pure — the tested contract)
# ---------------------------------------------------------------------------

def plan_plates(cartridge: WorldCartridge, only: set[str] | None = None) -> list[PlateJob]:
    """Compose the plate jobs for a cartridge. Pure, deterministic.

    Prompts are assembled from cartridge fields verbatim — no invention.
    Raises ValueError if the plan exceeds MAX_JOBS (refusal happens before
    any API call).
    """
    jobs: list[PlateJob] = []

    jobs.append(PlateJob(
        filename="settlement.png",
        prompt=(
            f"distant view of {cartridge.settlement}, "
            f"a {cartridge.settlement_type} in {cartridge.region}"
        ),
    ))
    home = cartridge.home_location
    jobs.append(PlateJob(
        filename="home.png",
        prompt=f"{home.name}, a {home.kind}; {home.condition}",
    ))
    faction = cartridge.faction
    jobs.append(PlateJob(
        filename="faction.png",
        prompt=f"the presence of {faction.name}, {faction.stance}; {faction.notes}",
    ))
    for npc in cartridge.family:
        jobs.append(PlateJob(
            filename=f"npc_{slugify(npc.name)}.png",
            prompt=f"portrait of {npc.name}, {npc.role}, {npc.trait}",
        ))

    if only:
        jobs = [j for j in jobs if j.filename.rsplit(".", 1)[0] in only]

    if len(jobs) > MAX_JOBS:
        raise ValueError(f"plan has {len(jobs)} jobs, the cap is {MAX_JOBS}")
    return jobs


def find_cartridge(world_id: str) -> WorldCartridge | None:
    """Locate a cartridge by world_id in the worlds dir. Fail-loud-per-file."""
    directory = _worlds_dir()
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.nyx-world.json")):
        try:
            cart = WorldCartridge.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"{path.name}: unreadable as a cartridge ({exc!r}), skipped")
            continue
        if cart.world_id == world_id:
            return cart
    return None


def _staging_dir(world_id: str) -> Path:
    """Staging only — never the live art dir (writes are structurally contained)."""
    return _worlds_dir() / "art" / "_staging" / world_id


# ---------------------------------------------------------------------------
# Execute (BFL + download + atomic staging write)
# ---------------------------------------------------------------------------

async def _download(client: httpx.AsyncClient, url: str) -> bytes | None:
    """Stream the image bytes. ≤ 2 same-URL retries; aborts at 8 MB."""
    for attempt in range(1 + DOWNLOAD_RETRIES):
        try:
            async with client.stream("GET", url, timeout=DOWNLOAD_TIMEOUT) as resp:
                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        logger.warning(f"download exceeds {MAX_DOWNLOAD_BYTES} B cap, aborted")
                        return None  # a too-big file will be too big again
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as exc:
            logger.warning(f"download attempt {attempt + 1} failed: {exc}")
    return None


def _write_atomic(path: Path, data: bytes) -> None:
    """Temp + os.replace on the same filesystem — idempotent overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


async def execute(jobs: list[PlateJob], world_id: str, api_key: str) -> int:
    """Paint every job into staging. Returns the number of FAILED jobs."""
    staging = _staging_dir(world_id)
    failed = 0

    async with httpx.AsyncClient() as client:
        for job in jobs:
            print(f"  painting {job.filename} ...")
            url = await generate_image(job.prompt, api_key=api_key, output_format="png")
            if not url:
                logger.warning(f"{job.filename}: generation failed")
                failed += 1
                continue

            data = await _download(client, url)
            if data is None:
                logger.warning(f"{job.filename}: download failed (generation NOT retried)")
                failed += 1
                continue

            target = staging / job.filename
            _write_atomic(target, data)
            note = ""
            if len(data) > SERVE_CAP_BYTES:
                note = f"  [!] {len(data)} B exceeds the 512 KB serve law — convert to webp before promoting"
                logger.warning(f"{job.filename}: {note.strip()}")
            print(f"  staged  {target}{note}")

    return failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="atelier",
        description="Generate a world's canonical plates into staging.",
    )
    parser.add_argument("--world", required=True, help="cartridge world_id")
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated stems (settlement,home,faction,npc_<slug>)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    args = parser.parse_args(argv)

    cartridge = find_cartridge(args.world)
    if cartridge is None:
        print(f"ERROR: no cartridge with world_id '{args.world}' in {_worlds_dir()}", file=sys.stderr)
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    try:
        jobs = plan_plates(cartridge, only=only)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not jobs:
        print("ERROR: --only matched no plates", file=sys.stderr)
        return 2

    print(f"The Atelier — {len(jobs)} plate(s) for '{args.world}':")
    for job in jobs:
        print(f"  {job.filename:32s} {job.prompt}")

    if args.dry_run:
        print("dry run — nothing painted.")
        return 0

    if not settings.bfl_api_key:
        print("ERROR: bfl_api_key is not configured (set BFL_API_KEY)", file=sys.stderr)
        return 2

    failed = asyncio.run(execute(jobs, args.world, settings.bfl_api_key))
    if failed:
        print(f"ERROR: {failed}/{len(jobs)} plate(s) failed; staging holds the rest", file=sys.stderr)
        return 1

    print(f"done — promote curated plates from {_staging_dir(args.world)} "
          f"to {_worlds_dir() / 'art' / args.world}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
