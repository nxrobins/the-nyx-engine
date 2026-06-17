"""init_pool — Postgres-to-SQLite fallback must not leak the asyncpg pool.

If PostgresStore.initialize() opens the pool (create_pool succeeds) but then the
schema execute raises, init_pool catches it and falls back to SQLite. The just-
created pool must be closed first — otherwise close_pool() can't reclaim it
(the global store now points at SQLite) and the connections leak for the
process lifetime.

Tested at the init_pool seam (mocking PostgresStore.initialize) so it does not
depend on asyncpg being installed — the real PostgresStore.close() is what
drains the pool.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_postgres_pool_closed_when_init_fails(monkeypatch, tmp_path):
    import app.db as db
    from app.core.config import settings
    from app.db.postgres_store import PostgresStore
    from app.db.sqlite_store import SQLiteStore

    closed = {"n": 0}

    class _FakePool:
        async def close(self):
            closed["n"] += 1

    async def _failing_initialize(self):
        # create_pool succeeded (pool opened) but the schema execute then raised.
        self._pool = _FakePool()
        raise RuntimeError("schema boom")

    monkeypatch.setattr(PostgresStore, "initialize", _failing_initialize)
    monkeypatch.setattr(settings, "database_url", "postgresql://fake/db")
    monkeypatch.setattr(settings, "sqlite_store_path", str(tmp_path / "fallback.sqlite3"))

    await db.close_pool()   # no _store carried over from another test
    await db.init_pool()
    try:
        # The opened pool was drained via the real PostgresStore.close(), not leaked...
        assert closed["n"] == 1
        # ...and we fell back to the SQLite backend.
        assert isinstance(db._store, SQLiteStore)
    finally:
        await db.close_pool()
