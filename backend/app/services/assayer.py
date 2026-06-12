"""The Assayer — death's second service: the life becomes a measurement.

Computes a PlayVerdict from the final thread state (pure — no LLM judges
a life), publishes it atomically into the assays/ artifact directory, and
aggregates per-world fitness for the evolution loop. The Worldsmith reads
verdicts at authoring time; worlds get bred against the only judge that
matters — the player.

Vitality (0-10) is deliberately transparent, not clever:

  span      — did the life get past childhood?            (0-4)
  clocks    — did the world's pressures mature?           (0-2)
  promises  — were the story's debts paid, not dropped?   (0-2)
  stakes    — did mortality participate (doom/oaths)?     (0-2)

A boring composite beats an opaque one: the Worldsmith needs direction,
not a leaderboard.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.schemas.assay import PlayVerdict
from app.schemas.cartridge import slugify
from app.schemas.state import ThreadState
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.assay")

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "assays"
_GLOB = "*.verdict.json"
_MAX_FILES = 2048


def assays_dir() -> Path:
    return Path(settings.assays_dir) if settings.assays_dir else _DEFAULT_DIR


# ---------------------------------------------------------------------------
# Computation (pure)
# ---------------------------------------------------------------------------

def compute_verdict(
    state: ThreadState,
    *,
    death_reason: str,
    book_id: str = "",
) -> PlayVerdict:
    """Weigh a finished life. Pure function of the terminal state."""
    session = state.session
    vectors = state.soul_ledger.vectors

    clocks_total = 0
    clocks_fired = 0
    if state.canon:
        clocks_total = len(state.canon.clocks)
        clocks_fired = sum(
            1 for c in state.canon.clocks.values() if c.progress >= c.max_segments
        )

    promises = state.ledger
    oaths = state.soul_ledger.active_oaths

    stamp = f"{session.player_id}:{session.run_number}"
    verdict_id = (
        f"{slugify(session.player_name).replace('_', '-')}-"
        f"{slugify(session.player_id).replace('_', '-')}-"
        f"r{session.run_number}-t{session.turn_count}"
    ).strip("-")[:120]

    return PlayVerdict(
        verdict_version=1,
        verdict_id=verdict_id,
        world_id=state.world_id or "unknown",
        thread_stamp=stamp,
        player_name=session.player_name,
        book_id=book_id,
        hamartia=state.soul_ledger.hamartia,
        died_turn=session.turn_count,
        epochs_reached=session.turn_count // 3,
        death_cause=death_reason[:600] or "unrecorded",
        doom_cause=state.doom.cause if state.doom.active else "",
        final_vectors={
            "metis": vectors.metis, "bia": vectors.bia,
            "kleos": vectors.kleos, "aidos": vectors.aidos,
        },
        imbalance=round(SoulVectorEngine.imbalance_score(vectors), 2),
        clocks_total=clocks_total,
        clocks_fired=clocks_fired,
        promises_planted=sum(1 for p in promises),
        promises_paid=sum(1 for p in promises if p.status == "paid"),
        promises_abandoned=sum(1 for p in promises if p.status == "abandoned"),
        oaths_sworn=len(oaths),
        oaths_fulfilled=sum(1 for o in oaths if o.status == "fulfilled"),
        oaths_broken=sum(1 for o in oaths if o.status == "broken"),
        pressures_at_death={
            k: round(v, 2)
            for k, v in state.pressures.model_dump().items()
            if isinstance(v, (int, float)) and k != "stability_streak" and v >= 0.1
        },
    )


# ---------------------------------------------------------------------------
# Publication + the shelf of weights
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_verdict(verdict: PlayVerdict) -> Path:
    path = assays_dir() / f"{verdict.verdict_id}.verdict.json"
    _atomic_write(path, verdict.model_dump_json(indent=2) + "\n")
    logger.info(f"Verdict written: {verdict.verdict_id} (world={verdict.world_id})")
    return path


def list_verdicts() -> list[PlayVerdict]:
    """Fail-loud-per-file: one bad verdict never hides the rest."""
    directory = assays_dir()
    if not directory.is_dir():
        return []
    verdicts: list[PlayVerdict] = []
    for path in sorted(directory.glob(_GLOB))[:_MAX_FILES]:
        try:
            verdicts.append(
                PlayVerdict.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except (ValidationError, UnicodeDecodeError, OSError) as exc:
            logger.warning(f"{path.name}: unreadable verdict ({exc!r}), skipped")
    return verdicts


# ---------------------------------------------------------------------------
# Fitness (aggregate, transparent)
# ---------------------------------------------------------------------------

def _vitality(lives: list[PlayVerdict]) -> float:
    """The boring composite. See module docstring for the weights."""
    n = len(lives)
    if n == 0:
        return 0.0

    avg_span = sum(v.died_turn for v in lives) / n
    span_score = min(avg_span / 12.0, 1.0) * 4.0   # turn 12+ average = full marks

    total_clocks = sum(v.clocks_total for v in lives)
    fired = sum(v.clocks_fired for v in lives)
    clock_score = (fired / total_clocks if total_clocks else 0.0) * 2.0

    planted = sum(v.promises_planted for v in lives)
    paid = sum(v.promises_paid for v in lives)
    promise_score = (paid / planted if planted else 0.0) * 2.0

    staked = sum(1 for v in lives if v.doom_cause or v.oaths_sworn > 0)
    stakes_score = (staked / n) * 2.0

    return round(span_score + clock_score + promise_score + stakes_score, 2)


def world_fitness(world_id: str | None = None) -> dict:
    """Aggregate verdicts into per-world fitness records.

    Returns {world_id: {lives, avg_died_turn, clock_fire_rate,
    promise_pay_rate, promise_abandon_rate, death_causes, vitality}}.
    Pass world_id to filter to one world.
    """
    verdicts = list_verdicts()
    by_world: dict[str, list[PlayVerdict]] = {}
    for v in verdicts:
        if world_id is not None and v.world_id != world_id:
            continue
        by_world.setdefault(v.world_id, []).append(v)

    report: dict[str, dict] = {}
    for wid, lives in sorted(by_world.items()):
        n = len(lives)
        total_clocks = sum(v.clocks_total for v in lives)
        planted = sum(v.promises_planted for v in lives)
        causes: dict[str, int] = {}
        for v in lives:
            key = v.doom_cause or "no_doom"
            causes[key] = causes.get(key, 0) + 1
        report[wid] = {
            "lives": n,
            "avg_died_turn": round(sum(v.died_turn for v in lives) / n, 1),
            "clock_fire_rate": round(
                sum(v.clocks_fired for v in lives) / total_clocks, 2
            ) if total_clocks else 0.0,
            "promise_pay_rate": round(
                sum(v.promises_paid for v in lives) / planted, 2
            ) if planted else 0.0,
            "promise_abandon_rate": round(
                sum(v.promises_abandoned for v in lives) / planted, 2
            ) if planted else 0.0,
            "death_causes": causes,
            "vitality": _vitality(lives),
        }
    return report
