"""SQLite-backed persistence for local Nyx play."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("nyx.db.sqlite")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id            TEXT NOT NULL,
    hamartia             TEXT NOT NULL,
    started_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at             TEXT,
    epitaph              TEXT,
    death_reason         TEXT,
    final_turn           INTEGER,
    is_dead              INTEGER NOT NULL DEFAULT 0,
    chronicle            TEXT NOT NULL DEFAULT '[]',
    factual_chronicle    TEXT NOT NULL DEFAULT '[]',
    final_soul_vectors   TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id       INTEGER NOT NULL,
    turn_number     INTEGER NOT NULL,
    action          TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    prose_summary   TEXT,
    soul_vectors    TEXT,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
);
"""


class SQLiteStore:
    """Durable local persistence using the Python stdlib sqlite3 module."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)
        logger.info(f"SQLite store ready: {self.path}")

    def _initialize_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()

    async def close(self) -> None:
        return

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def ensure_player(self, player_id: str) -> None:
        await asyncio.to_thread(self._ensure_player_sync, player_id)

    def _ensure_player_sync(self, player_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO players (player_id) VALUES (?)",
                (player_id,),
            )
            conn.commit()

    async def create_thread(self, player_id: str, hamartia: str) -> int | None:
        return await asyncio.to_thread(self._create_thread_sync, player_id, hamartia)

    def _create_thread_sync(self, player_id: str, hamartia: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO threads (player_id, hamartia) VALUES (?, ?)",
                (player_id, hamartia),
            )
            conn.commit()
            return int(cursor.lastrowid)

    async def update_thread_death(
        self,
        thread_id: int | None,
        epitaph: str,
        final_turn: int,
        *,
        death_reason: str = "",
        final_soul_vectors: dict | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._update_thread_death_sync,
            thread_id,
            epitaph,
            death_reason,
            final_turn,
            final_soul_vectors or {},
        )

    def _update_thread_death_sync(
        self,
        thread_id: int | None,
        epitaph: str,
        death_reason: str,
        final_turn: int,
        final_soul_vectors: dict,
    ) -> None:
        if thread_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                """UPDATE threads
                   SET is_dead = 1,
                       ended_at = CURRENT_TIMESTAMP,
                       epitaph = ?,
                       death_reason = ?,
                       final_turn = ?,
                       final_soul_vectors = ?
                   WHERE thread_id = ?""",
                (
                    epitaph,
                    death_reason,
                    final_turn,
                    json.dumps(final_soul_vectors),
                    thread_id,
                ),
            )
            conn.commit()

    async def create_turn(
        self,
        thread_id: int | None,
        turn_number: int,
        action: str,
        outcome: str,
        prose_summary: str,
        soul_vectors: dict,
    ) -> None:
        await asyncio.to_thread(
            self._create_turn_sync,
            thread_id,
            turn_number,
            action,
            outcome,
            prose_summary,
            soul_vectors,
        )

    def _create_turn_sync(
        self,
        thread_id: int | None,
        turn_number: int,
        action: str,
        outcome: str,
        prose_summary: str,
        soul_vectors: dict,
    ) -> None:
        if thread_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO turns
                   (thread_id, turn_number, action, outcome, prose_summary, soul_vectors)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    thread_id,
                    turn_number,
                    action,
                    outcome,
                    prose_summary,
                    json.dumps(soul_vectors),
                ),
            )
            conn.commit()

    async def append_chronicle(self, thread_id: int | None, sentence: str) -> None:
        await asyncio.to_thread(self._append_json_list_sync, thread_id, "chronicle", sentence)

    async def append_factual_chronicle(self, thread_id: int | None, digest: str) -> None:
        await asyncio.to_thread(
            self._append_json_list_sync,
            thread_id,
            "factual_chronicle",
            digest,
        )

    def _append_json_list_sync(self, thread_id: int | None, column: str, value: str) -> None:
        if thread_id is None or not value:
            return
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {column} FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            current = json.loads(row[column] if row and row[column] else "[]")
            current.append(value)
            conn.execute(
                f"UPDATE threads SET {column} = ? WHERE thread_id = ?",
                (json.dumps(current), thread_id),
            )
            conn.commit()

    async def get_dead_threads(self, player_id: str) -> list[dict]:
        return await asyncio.to_thread(self._get_dead_threads_sync, player_id)

    def _get_dead_threads_sync(self, player_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT thread_id, epitaph, hamartia, death_reason, final_turn, final_soul_vectors
                   FROM threads
                   WHERE player_id = ? AND is_dead = 1
                   ORDER BY ended_at DESC, thread_id DESC""",
                (player_id,),
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            result.append(
                {
                    "thread_id": row["thread_id"],
                    "epitaph": row["epitaph"],
                    "hamartia": row["hamartia"],
                    "death_reason": row["death_reason"],
                    "final_turn": row["final_turn"],
                    "soul_vectors": json.loads(row["final_soul_vectors"] or "{}"),
                }
            )
        return result

    async def get_last_ancestor(self, player_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_last_ancestor_sync, player_id)

    def _get_last_ancestor_sync(self, player_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT thread_id, epitaph, hamartia, death_reason, final_turn, final_soul_vectors
                   FROM threads
                   WHERE player_id = ? AND is_dead = 1 AND epitaph IS NOT NULL
                   ORDER BY ended_at DESC, thread_id DESC
                   LIMIT 1""",
                (player_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "thread_id": row["thread_id"],
            "epitaph": row["epitaph"],
            "hamartia": row["hamartia"],
            "death_reason": row["death_reason"],
            "final_turn": row["final_turn"],
            "soul_vectors": json.loads(row["final_soul_vectors"] or "{}"),
        }
