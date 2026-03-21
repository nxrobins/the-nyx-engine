"""Nyx persistence facade — SQLite by default, PostgreSQL when configured."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.db.store import ThreadStore

logger = logging.getLogger("nyx.db")

_store: ThreadStore | None = None


def _default_sqlite_path() -> Path:
    if settings.sqlite_store_path:
        return Path(settings.sqlite_store_path)
    return Path(__file__).resolve().parents[2] / "nyx_engine.sqlite3"


async def init_pool() -> None:
    """Initialize the active persistence backend."""
    global _store

    if _store is not None:
        return

    if settings.database_url:
        try:
            from app.db.postgres_store import PostgresStore

            store = PostgresStore(settings.database_url)
            await store.initialize()
            _store = store
            return
        except Exception as exc:
            logger.error(f"PostgreSQL store init failed: {exc}. Falling back to SQLite.")

    from app.db.sqlite_store import SQLiteStore

    store = SQLiteStore(_default_sqlite_path())
    await store.initialize()
    _store = store


async def close_pool() -> None:
    """Close the active persistence backend."""
    global _store
    if _store is None:
        return
    await _store.close()
    _store = None


async def ensure_player(player_id: str) -> None:
    if _store is None:
        return
    await _store.ensure_player(player_id)


async def create_thread(player_id: str, hamartia: str) -> int | None:
    if _store is None:
        return None
    return await _store.create_thread(player_id, hamartia)


async def update_thread_death(
    thread_id: int | None,
    epitaph: str,
    final_turn: int,
    *,
    death_reason: str = "",
    final_soul_vectors: dict | None = None,
) -> None:
    if _store is None:
        return
    await _store.update_thread_death(
        thread_id,
        epitaph,
        final_turn,
        death_reason=death_reason,
        final_soul_vectors=final_soul_vectors,
    )


async def create_turn(
    thread_id: int | None,
    turn_number: int,
    action: str,
    outcome: str,
    prose_summary: str,
    soul_vectors: dict,
) -> None:
    if _store is None:
        return
    await _store.create_turn(
        thread_id,
        turn_number,
        action,
        outcome,
        prose_summary,
        soul_vectors,
    )


async def append_chronicle(thread_id: int | None, sentence: str) -> None:
    if _store is None:
        return
    await _store.append_chronicle(thread_id, sentence)


async def append_factual_chronicle(thread_id: int | None, digest: str) -> None:
    if _store is None:
        return
    await _store.append_factual_chronicle(thread_id, digest)


async def get_dead_threads(player_id: str) -> list[dict]:
    if _store is None:
        return []
    return await _store.get_dead_threads(player_id)


async def get_last_ancestor(player_id: str) -> dict | None:
    if _store is None:
        return None
    return await _store.get_last_ancestor(player_id)
