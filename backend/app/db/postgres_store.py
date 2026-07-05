"""PostgreSQL-backed persistence retained as an optional backend."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("nyx.db.postgres")


def _as_dict(value: object) -> dict:
    """Decode a JSON/JSONB column to a dict.

    asyncpg returns JSON/JSONB as a raw str unless a type codec is registered
    (this store registers none), so the read side must json.loads it — mirroring
    SQLite's json.loads and the write side's json.dumps. dict("{...}") would
    raise ValueError. Defensive against str, None/empty, and an already-decoded
    dict (so registering a codec later stays safe).
    """
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    return json.loads(value)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id           SERIAL PRIMARY KEY,
    player_id           TEXT NOT NULL REFERENCES players(player_id),
    hamartia            TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    epitaph             TEXT,
    death_reason        TEXT,
    final_turn          INT,
    is_dead             BOOLEAN NOT NULL DEFAULT FALSE,
    chronicle           JSONB NOT NULL DEFAULT '[]'::jsonb,
    factual_chronicle   JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_soul_vectors  JSONB NOT NULL DEFAULT '{}'::jsonb
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

CREATE TABLE IF NOT EXISTS thread_snapshots (
    token           TEXT PRIMARY KEY,
    player_id       TEXT NOT NULL,
    thread_id       INT,
    turn_count      INT NOT NULL,
    schema_version  INT NOT NULL,
    state_json      TEXT NOT NULL,
    chapters_json   TEXT NOT NULL DEFAULT '[]',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresStore:
    """Optional asyncpg-backed persistence."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool = None

    async def initialize(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=2,
            max_size=10,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA_SQL)
        logger.info("PostgreSQL store ready.")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ensure_player(self, player_id: str) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO players (player_id) VALUES ($1) ON CONFLICT DO NOTHING",
                player_id,
            )

    async def create_thread(self, player_id: str, hamartia: str) -> int | None:
        if not self._pool:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO threads (player_id, hamartia) VALUES ($1, $2) RETURNING thread_id",
                player_id,
                hamartia,
            )
        return int(row["thread_id"]) if row else None

    async def update_thread_death(
        self,
        thread_id: int | None,
        epitaph: str,
        final_turn: int,
        *,
        death_reason: str = "",
        final_soul_vectors: dict | None = None,
    ) -> None:
        if not self._pool or thread_id is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET is_dead = TRUE,
                       ended_at = NOW(),
                       epitaph = $1,
                       death_reason = $2,
                       final_turn = $3,
                       final_soul_vectors = $4::jsonb
                   WHERE thread_id = $5""",
                epitaph,
                death_reason,
                final_turn,
                json.dumps(final_soul_vectors or {}),
                thread_id,
            )

    async def create_turn(
        self,
        thread_id: int | None,
        turn_number: int,
        action: str,
        outcome: str,
        prose_summary: str,
        soul_vectors: dict,
    ) -> None:
        if not self._pool or thread_id is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO turns
                   (thread_id, turn_number, action, outcome, prose_summary, soul_vectors)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
                thread_id,
                turn_number,
                action,
                outcome,
                prose_summary,
                json.dumps(soul_vectors),
            )

    async def append_chronicle(self, thread_id: int | None, sentence: str) -> None:
        if not self._pool or thread_id is None or not sentence:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET chronicle = chronicle || $1::jsonb
                   WHERE thread_id = $2""",
                json.dumps([sentence]),
                thread_id,
            )

    async def append_factual_chronicle(self, thread_id: int | None, digest: str) -> None:
        if not self._pool or thread_id is None or not digest:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE threads
                   SET factual_chronicle = factual_chronicle || $1::jsonb
                   WHERE thread_id = $2""",
                json.dumps([digest]),
                thread_id,
            )

    async def save_snapshot(
        self,
        token: str,
        player_id: str,
        thread_id: int | None,
        turn_count: int,
        schema_version: int,
        state_json: str,
        chapters_json: str,
    ) -> None:
        if not self._pool:
            return
        async with self._pool.acquire() as conn:
            # SC-3/CF-2: latest-wins by turn_count; an older write is refused.
            await conn.execute(
                """INSERT INTO thread_snapshots
                       (token, player_id, thread_id, turn_count, schema_version,
                        state_json, chapters_json, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                   ON CONFLICT (token) DO UPDATE SET
                       player_id=excluded.player_id,
                       thread_id=excluded.thread_id,
                       turn_count=excluded.turn_count,
                       schema_version=excluded.schema_version,
                       state_json=excluded.state_json,
                       chapters_json=excluded.chapters_json,
                       updated_at=NOW()
                   WHERE excluded.turn_count > thread_snapshots.turn_count""",
                token, player_id, thread_id, turn_count, schema_version,
                state_json, chapters_json,
            )

    async def load_snapshot(self, token: str) -> dict | None:
        if not self._pool:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT token, player_id, thread_id, turn_count, schema_version,
                          state_json, chapters_json
                   FROM thread_snapshots WHERE token = $1""",
                token,
            )
        if not row:
            return None
        return {
            "token": row["token"],
            "player_id": row["player_id"],
            "thread_id": row["thread_id"],
            "turn_count": row["turn_count"],
            "schema_version": row["schema_version"],
            "state_json": row["state_json"],
            "chapters_json": row["chapters_json"],
        }

    async def get_dead_threads(self, player_id: str) -> list[dict]:
        if not self._pool:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT thread_id, epitaph, hamartia, death_reason, final_turn, final_soul_vectors
                   FROM threads
                   WHERE player_id = $1 AND is_dead = TRUE
                   ORDER BY ended_at DESC, thread_id DESC""",
                player_id,
            )
        return [
            {
                "thread_id": row["thread_id"],
                "epitaph": row["epitaph"],
                "hamartia": row["hamartia"],
                "death_reason": row["death_reason"],
                "final_turn": row["final_turn"],
                "soul_vectors": _as_dict(row["final_soul_vectors"]),
            }
            for row in rows
        ]

    async def get_last_ancestor(self, player_id: str) -> dict | None:
        if not self._pool:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT thread_id, epitaph, hamartia, death_reason, final_turn, final_soul_vectors
                   FROM threads
                   WHERE player_id = $1 AND is_dead = TRUE AND epitaph IS NOT NULL
                   ORDER BY ended_at DESC, thread_id DESC
                   LIMIT 1""",
                player_id,
            )
        if not row:
            return None
        return {
            "thread_id": row["thread_id"],
            "epitaph": row["epitaph"],
            "hamartia": row["hamartia"],
            "death_reason": row["death_reason"],
            "final_turn": row["final_turn"],
            "soul_vectors": _as_dict(row["final_soul_vectors"]),
        }
