"""Nyx Engine — Optional PostgreSQL Persistence Layer.

Graceful no-op when DATABASE_URL is empty: every public function guards
`if not _pool: return` so the game runs identically in-memory.

Schema auto-created on pool init:
  - players:  player identity
  - threads:  one per game run (hamartia → death/epitaph)
  - turns:    per-turn snapshots (action, outcome, soul vectors)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("nyx.db")

# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------

_pool = None  # asyncpg.Pool | None


async def init_pool() -> None:
    """Create the asyncpg connection pool and bootstrap schema.

    No-op if DATABASE_URL is empty.
    """
    global _pool

    if not settings.database_url:
        logger.info("DATABASE_URL not set — running in-memory only.")
        return

    try:
        import asyncpg
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
        )
        logger.info("PostgreSQL pool created.")
        await _bootstrap_schema()
    except Exception as e:
        logger.error(f"DB pool init failed: {e}. Continuing in-memory.")
        _pool = None


async def close_pool() -> None:
    """Drain and close the pool. No-op if no pool."""
    global _pool
    if not _pool:
        return
    await _pool.close()
    _pool = None
    logger.info("PostgreSQL pool closed.")


# ---------------------------------------------------------------------------
# Schema Bootstrap
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id   SERIAL PRIMARY KEY,
    player_id   TEXT NOT NULL REFERENCES players(player_id),
    hamartia    TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    epitaph     TEXT,
    final_turn  INT,
    is_dead     BOOLEAN NOT NULL DEFAULT FALSE,
    chronicle           JSONB NOT NULL DEFAULT '[]'::jsonb,
    factual_chronicle   JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id       SERIAL PRIMARY KEY,
    thread_id     INT NOT NULL REFERENCES threads(thread_id),
    turn_number   INT NOT NULL,
    action        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    prose_summary TEXT,
    soul_vectors  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def _bootstrap_schema() -> None:
    """Run CREATE TABLE IF NOT EXISTS for all tables."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
    logger.info("DB schema verified.")


# ---------------------------------------------------------------------------
# CRUD Functions
# ---------------------------------------------------------------------------

async def ensure_player(player_id: str) -> None:
    """INSERT player row if it doesn't already exist. No-op without DB."""
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO players (player_id) VALUES ($1) ON CONFLICT DO NOTHING",
                player_id,
            )
    except Exception as e:
        logger.error(f"ensure_player failed: {e}")


async def create_thread(player_id: str, hamartia: str) -> Optional[int]:
    """Create a new thread row. Returns thread_id, or None without DB."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO threads (player_id, hamartia) VALUES ($1, $2) RETURNING thread_id",
                player_id, hamartia,
            )
            thread_id = row["thread_id"]
            logger.info(f"Thread {thread_id} created for player {player_id}")
            return thread_id
    except Exception as e:
        logger.error(f"create_thread failed: {e}")
        return None


async def update_thread_death(
    thread_id: Optional[int],
    epitaph: str,
    final_turn: int,
) -> None:
    """Mark a thread as dead with its epitaph. No-op without DB or thread_id."""
    if not _pool or thread_id is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET is_dead = TRUE, ended_at = NOW(),
                       epitaph = $1, final_turn = $2
                   WHERE thread_id = $3""",
                epitaph, final_turn, thread_id,
            )
            logger.info(f"Thread {thread_id} marked dead at turn {final_turn}")
    except Exception as e:
        logger.error(f"update_thread_death failed: {e}")


async def create_turn(
    thread_id: Optional[int],
    turn_number: int,
    action: str,
    outcome: str,
    prose_summary: str,
    soul_vectors: dict,
) -> None:
    """Persist a single turn snapshot. No-op without DB or thread_id.

    IMPORTANT: asyncpg does NOT auto-serialize dicts to JSONB.
    We explicitly json.dumps() the soul_vectors before passing.
    """
    if not _pool or thread_id is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO turns
                   (thread_id, turn_number, action, outcome, prose_summary, soul_vectors)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
                thread_id, turn_number, action, outcome,
                prose_summary, json.dumps(soul_vectors),
            )
    except Exception as e:
        logger.error(f"create_turn failed: {e}")


async def append_chronicle(thread_id: Optional[int], sentence: str) -> None:
    """Append a mythic sentence to the thread's chronicle array. No-op without DB."""
    if not _pool or thread_id is None or not sentence:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET chronicle = chronicle || $1::jsonb
                   WHERE thread_id = $2""",
                json.dumps([sentence]), thread_id,
            )
            logger.info(f"Chronicle appended to thread {thread_id}")
    except Exception as e:
        logger.error(f"append_chronicle failed: {e}")


async def append_factual_chronicle(thread_id: Optional[int], digest: str) -> None:
    """Append a factual digest to the thread's factual_chronicle array. No-op without DB."""
    if not _pool or thread_id is None or not digest:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET factual_chronicle = factual_chronicle || $1::jsonb
                   WHERE thread_id = $2""",
                json.dumps([digest]), thread_id,
            )
            logger.info(f"Factual chronicle appended to thread {thread_id}")
    except Exception as e:
        logger.error(f"append_factual_chronicle failed: {e}")


async def get_dead_threads(player_id: str) -> list[dict]:
    """All dead threads for a player, with final soul vectors via JOIN."""
    if not _pool:
        return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT t.thread_id, t.epitaph, t.hamartia, t.final_turn,
                          tn.soul_vectors
                   FROM threads t
                   LEFT JOIN turns tn ON tn.thread_id = t.thread_id
                                      AND tn.turn_number = t.final_turn
                   WHERE t.player_id = $1 AND t.is_dead = TRUE
                   ORDER BY t.ended_at DESC""",
                player_id,
            )
        result = []
        for r in rows:
            d = dict(r)
            # asyncpg may return JSONB as str — deserialize if needed
            if isinstance(d.get("soul_vectors"), str):
                d["soul_vectors"] = json.loads(d["soul_vectors"])
            result.append(d)
        return result
    except Exception as e:
        logger.error(f"get_dead_threads failed: {e}")
        return []


async def get_last_ancestor(player_id: str) -> Optional[dict]:
    """Query the most recent dead thread's epitaph for Ancestral Echo.

    Returns dict with 'epitaph', 'hamartia', 'final_turn' or None.
    """
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT epitaph, hamartia, final_turn
                   FROM threads
                   WHERE player_id = $1 AND is_dead = TRUE AND epitaph IS NOT NULL
                   ORDER BY ended_at DESC
                   LIMIT 1""",
                player_id,
            )
            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"get_last_ancestor failed: {e}")
        return None
