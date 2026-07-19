"""Resume — rehydrate a living/dead thread from its token (durability sub-slice 3).

Covers kernel rehydration (schema-version match / mismatch / corruption) and the
/resume endpoint's constraints: SC-2 (one live kernel per thread), SC-4/CF-1
(unknown token 404s), SC-5 (stale schema 404s, corruption 500s), SC-6 (terminal
rehydrates terminal), and the full evict→resume cycle continuing a life.
"""

from __future__ import annotations

import app.db as db
import pytest
from fastapi import HTTPException

from app.api import routes
from app.api.routes import init_session, resume_session
from app.core.config import settings
from app.core.kernel import NyxKernel
from app.schemas.state import InitRequest, ResumeRequest, ThreadState
from app.services.durability import SNAPSHOT_SCHEMA_VERSION, serialize_snapshot


def _snapshot_of(state: ThreadState, *, version: int = SNAPSHOT_SCHEMA_VERSION, thread_id: int = 7) -> dict:
    state_json, chapters_json = serialize_snapshot(state, [])
    return {
        "token": "tok", "player_id": "p1", "thread_id": thread_id,
        "turn_count": state.session.turn_count, "schema_version": version,
        "state_json": state_json, "chapters_json": chapters_json,
    }


class TestRehydrate:
    def test_version_match_restores_state(self):
        s = ThreadState()
        s.session.turn_count = 5
        s.session.player_name = "Hero"
        k = NyxKernel.rehydrate(_snapshot_of(s), "tok")
        assert k is not None
        assert k.state == s
        assert k._resume_token == "tok"
        assert k._thread_id == 7

    def test_version_mismatch_returns_none(self):
        s = ThreadState()
        assert NyxKernel.rehydrate(_snapshot_of(s, version=999), "tok") is None

    def test_corruption_at_current_version_raises(self):
        bad = {
            "token": "tok", "player_id": "p", "thread_id": 1, "turn_count": 1,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "state_json": "{ this is not valid json",
            "chapters_json": "[]",
        }
        with pytest.raises(Exception):
            NyxKernel.rehydrate(bad, "tok")

    def test_terminal_snapshot_rehydrates_terminal(self):
        s = ThreadState()
        s.terminal = True
        s.death_reason = "An oath was broken."
        k = NyxKernel.rehydrate(_snapshot_of(s), "tok")
        assert k.state.terminal is True


@pytest.fixture
async def with_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sqlite_store_path", str(tmp_path / "resume.sqlite3"))
    await db.init_pool()
    yield
    await db.close_pool()


async def _init_one() -> tuple[str, str, NyxKernel]:
    result = await init_session(InitRequest(
        hamartia="Unformed", player_id="p1", name="Hero", gender="boy",
        first_memory="The weight of a heavy stone in my hand.",
    ))
    sid = result.session_id
    return sid, result.resume_token, routes._sessions[sid].kernel


class TestResumeConcurrency:
    """V2-C1: two concurrent resumes of ONE token must never mint two kernels.
    The critical section spans an await (load_snapshot); without the lock both
    calls pass the empty scan and register — a stale twin could later overwrite a
    terminal snapshot and un-kill a death."""

    @pytest.mark.asyncio
    async def test_concurrent_resume_of_one_token_mints_one_kernel(self, with_store):
        import asyncio
        sid, token, _ = await _init_one()
        routes._sessions.pop(sid)  # evict: resumable, not live
        before = len(routes._sessions)

        a, b = await asyncio.gather(
            resume_session(ResumeRequest(resume_token=token)),
            resume_session(ResumeRequest(resume_token=token)),
        )
        # Exactly ONE new session; both callers see the same session_id.
        assert len(routes._sessions) == before + 1
        assert a.session_id == b.session_id
        # And that one kernel is the sole holder of the token.
        holders = [e for e in routes._sessions.values() if e.kernel._resume_token == token]
        assert len(holders) == 1


class TestResumeEndpoint:
    @pytest.mark.asyncio
    async def test_init_exposes_a_resume_token(self, with_store):
        _, token, _ = await _init_one()
        assert token  # the client gets a handle to persist

    @pytest.mark.asyncio
    async def test_unknown_token_404s(self, with_store):
        with pytest.raises(HTTPException) as exc:
            await resume_session(ResumeRequest(resume_token="does-not-exist"))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_live_session_is_reused_not_duplicated(self, with_store):
        sid, token, _ = await _init_one()
        n_before = len(routes._sessions)
        result = await resume_session(ResumeRequest(resume_token=token))
        # SC-2: the same live session is returned; no second kernel is minted.
        assert result.session_id == sid
        assert len(routes._sessions) == n_before

    @pytest.mark.asyncio
    async def test_evicted_thread_resumes_from_snapshot(self, with_store):
        sid, token, kernel = await _init_one()
        await kernel.process_turn("I haul the ore up the ladder")
        live_turn = kernel.state.session.turn_count
        live_state = kernel.state

        # Simulate eviction / restart: the session is gone, the snapshot remains.
        routes._sessions.pop(sid)

        result = await resume_session(ResumeRequest(resume_token=token))
        assert result.session_id != sid                       # a fresh session
        new_kernel = routes._sessions[result.session_id].kernel
        assert new_kernel.state.session.turn_count == live_turn
        assert new_kernel.state == live_state                 # faithfully restored
        # ...and the resumed thread can keep living.
        await new_kernel.process_turn("I catch my breath and look around")
        assert new_kernel.state.session.turn_count == live_turn + 1

    @pytest.mark.asyncio
    async def test_terminal_thread_resumes_terminal(self, with_store):
        sid, token, kernel = await _init_one()
        # A death happens at a later turn than birth — so its snapshot's higher
        # turn_count wins the monotonic guard (a same-turn write would be refused).
        kernel.state.session.turn_count = 5
        kernel.state.terminal = True
        kernel.state.death_reason = "You chose oblivion."
        await kernel._snapshot_now()
        routes._sessions.pop(sid)

        result = await resume_session(ResumeRequest(resume_token=token))
        assert result.terminal is True
        assert result.death_reason == "You chose oblivion."
