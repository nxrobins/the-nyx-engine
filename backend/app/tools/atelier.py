"""The Atelier — authoring-time plate generation for world cartridges.

    python -m app.tools.atelier --world <world_id> [--only settlement,home] [--dry-run]

Generates the canonical image set for one world — settlement, home, faction,
one portrait per family NPC — from **cartridge facts only**: names, kinds,
conditions, traits, and a shared world-mood clause drawn from the cartridge's
visual `world_facts` (the place's look, not the narrative situation). Nothing is invented; plates depict what
the cartridge declares (the anti-hallucination rule, applied to pixels). The
sumi-e style wrap comes from ``generate_image`` exactly as for milestones.

Plan/execute split:
  - ``plan_plates(cartridge)`` is pure and deterministic — the tested
    producer/consumer contract (every filename matches ``plates._PLATE_RE``;
    NPC stems are canon npc_ids verbatim; per-plate seeds are stable).
  - ``execute(jobs)`` calls BFL with ``output_format="jpeg"`` and the per-plate
    seed, downloads the bytes immediately (BFL URLs expire), and writes
    atomically to STAGING ONLY: ``worlds/art/_staging/{world_id}/``. Promotion
    into the live ``worlds/art/{world_id}/`` is the human curation step.

The dumb limits (the Constraints & Fallbacks matrix, made executable):
  - jpeg, because BFL cannot produce webp; small + directly promotable.
  - ≤ MAX_JOBS jobs/world (refuse, exit 2, before any API call).
  - prompts bounded: mood ≤ MAX_MOOD_CHARS, subject ≤ MAX_PROMPT_CHARS so the
    final wrapped prompt stays ≤ 480 chars (AT-E3) — style + subject lead.
  - dimensions are BFL's fixed 1024×768, never cartridge-derived (AT-E6).
  - 30 s download timeout; streamed read aborts at 8 MB; ≤ 2 same-URL retries,
    generation never re-paid.
  - **a downloaded plate over the 512 KB serve cap FAILS the job and is not
    staged** (AT-E2) — "promotable" means "serveable"; the curator never
    promotes an unservable plate. Moderation/terminal BFL failures fail fast
    (AT-E1, in ``generate_image``).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024  # staging download RAM guard
DOWNLOAD_RETRIES = 2               # same-URL retries; generation is never re-paid
SERVE_CAP_BYTES = 524_288           # the live 512 KB serve law (AT-E2: enforced, not warned)

# Art direction: the people of the Age of Ash are Black/Brown. The cartridge
# schema carries no appearance field, so this is a named, tunable adjective
# phrase, applied to portraits AND faction crowds (placed early in each prompt
# so the length cap never truncates it).
PEOPLE_DESCRIPTOR = "dark-skinned Black"

MAX_MOOD_CHARS = 140                # AT-E3: the shared world-mood clause
# AT-E3: subject cap so prefix + ", " + subject + ", " + suffix ≤ 480 chars.
_WRAP_OVERHEAD = len(settings.bfl_style_prefix) + len(settings.bfl_style_suffix) + 4
MAX_PROMPT_CHARS = max(80, 480 - _WRAP_OVERHEAD)


@dataclass(frozen=True)
class PlateJob:
    """One plate to paint: a lawful filename, a canon-fact prompt, a stable seed."""
    filename: str
    prompt: str
    seed: int


# ---------------------------------------------------------------------------
# Plan (pure — the tested contract)
# ---------------------------------------------------------------------------

def _bounded(text: str, limit: int) -> str:
    """Collapse whitespace and truncate to ≤ limit chars at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut).rstrip(" ,;.")


def _world_mood(cartridge: WorldCartridge) -> str:
    """A short shared mood clause from the world's *visual* facts — the place's
    look (geography, materials, light), not the narrative `active_situation`
    (which is the player's tension, not an establishing image). Threads through
    the world-scale plates so they cohere. Bounded (AT-E3)."""
    facts = [f.strip().rstrip(".") for f in cartridge.world_facts[:2] if f.strip()]
    return _bounded("; ".join(facts), MAX_MOOD_CHARS)


def _seed(world_id: str, stem: str) -> int:
    """Deterministic per-plate seed (32-bit, in BFL's range) — reproducible,
    varied across a world's plates."""
    return int(hashlib.sha256(f"{world_id}:{stem}".encode("utf-8")).hexdigest()[:8], 16)


def plan_plates(cartridge: WorldCartridge, only: set[str] | None = None) -> list[PlateJob]:
    """Compose the plate jobs for a cartridge. Pure, deterministic.

    Prompts are assembled from cartridge fields verbatim — no invention — and
    bounded (AT-E3). Raises ValueError if the plan exceeds MAX_JOBS (refusal
    before any API call).
    """
    wid = cartridge.world_id
    mood = _world_mood(cartridge)
    home = cartridge.home_location
    faction = cartridge.faction

    raw: list[tuple[str, str]] = [
        ("settlement",
         f"distant view of {cartridge.settlement}, a {cartridge.settlement_type} "
         f"in {cartridge.region}; {mood}"),
        ("home",
         f"interior of {home.name}, a {home.kind} in {cartridge.settlement}; "
         f"{home.condition}; {mood}"),
        ("faction",
         f"the presence of {faction.name}, {PEOPLE_DESCRIPTOR} people, in "
         f"{cartridge.settlement}, {faction.stance}; {faction.notes}; {mood}"),
    ]
    for npc in cartridge.family:
        raw.append((
            f"npc_{slugify(npc.name)}",
            f"portrait of a {PEOPLE_DESCRIPTOR} person, {npc.name}, {npc.role} of "
            f"{cartridge.settlement}; {npc.trait}",
        ))

    jobs = [
        PlateJob(filename=f"{stem}.jpg", prompt=_bounded(prompt, MAX_PROMPT_CHARS),
                 seed=_seed(wid, stem))
        for stem, prompt in raw
    ]

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
    """Paint every job into staging. Returns the number of FAILED jobs.

    AT-E2: a plate over the serve cap fails the job and is NOT staged — the
    curator never sees, and so never promotes, an unservable plate.
    """
    staging = _staging_dir(world_id)
    failed = 0

    async with httpx.AsyncClient() as client:
        for job in jobs:
            print(f"  painting {job.filename} ...")
            url = await generate_image(
                job.prompt, api_key=api_key, output_format="jpeg", seed=job.seed
            )
            if not url:
                logger.warning(f"{job.filename}: generation failed (moderation/error/timeout)")
                failed += 1
                continue

            data = await _download(client, url)
            if data is None:
                logger.warning(f"{job.filename}: download failed (generation NOT retried)")
                failed += 1
                continue

            if len(data) > SERVE_CAP_BYTES:  # AT-E2: never stage what serve would 413
                logger.warning(
                    f"{job.filename}: {len(data)} B > {SERVE_CAP_BYTES} serve cap — "
                    f"rejected, not staged (regenerate)"
                )
                failed += 1
                continue

            target = staging / job.filename
            _write_atomic(target, data)
            print(f"  staged  {target} ({len(data)} B)")

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
        print(f"  {job.filename:28s} [seed {job.seed}] {job.prompt}")

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
