"""Snapshot-on-commit — the durability write path (THE THREAD PERSISTS, sub-slice 2).

Covers the store's monotonic latest-wins guard (SC-3/CF-2), the size ceiling
(CF-4), the resume-token shape (SC-4), DB-less no-op, and the kernel writing a
snapshot after every committed turn (SC-1: state + the Scribe's chapters).
"""

from __future__ import annotations

import app.db as db
import pytest
from app.core.config import settings
from app.core.kernel import NyxKernel
from app.db.sqlite_store import SQLiteStore
from app.schemas.state import ThreadState
from app.services.durability import (
    SNAPSHOT_MAX_BYTES,
    SNAPSHOT_SCHEMA_VERSION,
    mint_resume_token,
    serialize_snapshot,
)


def test_resume_token_is_opaque_and_unique():
    a, b = mint_resume_token(), mint_resume_token()
    assert a != b
    assert len(a) >= 32 and "/" not in a and "+" not in a  # url-safe, ~256-bit


def test_serialize_rejects_oversized_payload_loudly():
    s = ThreadState()
    s.world_context = "x" * (SNAPSHOT_MAX_BYTES + 10)  # blow the ceiling
    assert serialize_snapshot(s, []) is None            # CF-4: skip, not truncate


def test_serialize_normal_state_returns_json_pair():
    s = ThreadState()
    s.session.turn_count = 3
    payload = serialize_snapshot(s, [])
    assert payload is not None
    state_json, chapters_json = payload
    assert ThreadState.model_validate_json(state_json).session.turn_count == 3
    assert chapters_json == "[]"


class TestSnapshotStore:
    @pytest.fixture
    async def store(self, tmp_path):
        st = SQLiteStore(tmp_path / "dur.sqlite3")
        await st.initialize()
        return st

    @pytest.mark.asyncio
    async def test_save_then_load_round_trips(self, store):
        s = ThreadState()
        s.session.turn_count = 7
        s.session.player_name = "Hero"
        state_json, chapters_json = serialize_snapshot(s, [])
        await store.save_snapshot("tok1", "p1", 42, 7, SNAPSHOT_SCHEMA_VERSION, state_json, chapters_json)

        loaded = await store.load_snapshot("tok1")
        assert loaded is not None
        assert loaded["turn_count"] == 7
        assert loaded["player_id"] == "p1"
        assert loaded["thread_id"] == 42
        assert loaded["schema_version"] == SNAPSHOT_SCHEMA_VERSION
        restored = ThreadState.model_validate_json(loaded["state_json"])
        assert restored == s

    @pytest.mark.asyncio
    async def test_load_unknown_token_is_none(self, store):
        assert await store.load_snapshot("nope") is None

    @pytest.mark.asyncio
    async def test_monotonic_guard_refuses_stale_write(self, store):
        newer = serialize_snapshot(_state_at(turn=5, name="turn5"), [])[0]
        older = serialize_snapshot(_state_at(turn=3, name="turn3"), [])[0]
        await store.save_snapshot("tok", "p", 1, 5, 1, newer, "[]")
        await store.save_snapshot("tok", "p", 1, 3, 1, older, "[]")  # stale — must not clobber
        loaded = await store.load_snapshot("tok")
        assert loaded["turn_count"] == 5
        assert ThreadState.model_validate_json(loaded["state_json"]).session.player_name == "turn5"

    @pytest.mark.asyncio
    async def test_newer_write_wins(self, store):
        await store.save_snapshot("tok", "p", 1, 3, 1, serialize_snapshot(_state_at(3, "old"), [])[0], "[]")
        await store.save_snapshot("tok", "p", 1, 8, 1, serialize_snapshot(_state_at(8, "new"), [])[0], "[]")
        loaded = await store.load_snapshot("tok")
        assert loaded["turn_count"] == 8
        assert ThreadState.model_validate_json(loaded["state_json"]).session.player_name == "new"


@pytest.mark.asyncio
async def test_facade_is_noop_without_a_store():
    # The hermetic suite never calls init_pool, so _store is None.
    assert db._store is None
    await db.save_snapshot("t", "p", 1, 1, 1, "{}", "[]")  # must not raise
    assert await db.load_snapshot("t") is None


@pytest.mark.asyncio
async def test_kernel_snapshots_each_committed_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sqlite_store_path", str(tmp_path / "k.sqlite3"))
    await db.init_pool()
    try:
        k = NyxKernel()
        await k.initialize(
            hamartia="Unformed", player_id="p1", name="Hero", gender="boy",
            first_memory="The weight of a heavy stone in my hand.",
        )
        assert k._resume_token  # minted at birth

        snap = await db.load_snapshot(k._resume_token)
        assert snap is not None and snap["turn_count"] == 1  # born, snapshotted

        await k.process_turn("I haul the ore up the ladder")
        snap2 = await db.load_snapshot(k._resume_token)
        assert snap2["turn_count"] == k.state.session.turn_count
        # The snapshot round-trips to the live state.
        assert ThreadState.model_validate_json(snap2["state_json"]) == k.state
    finally:
        await db.close_pool()


def _state_at(turn: int, name: str) -> ThreadState:
    s = ThreadState()
    s.session.turn_count = turn
    s.session.player_name = name
    return s
