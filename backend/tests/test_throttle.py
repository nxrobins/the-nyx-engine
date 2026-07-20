"""The Throttle — reliability bounds (config, visible degradation, sessions).

All hermetic + keyless: the real-model path is exercised by monkeypatching
litellm.acompletion (or an agent's model off "mock") and forcing deterministic
raises — nothing dials out. The autouse conftest fixture resets the degraded
counter, _sessions, and the llm budget per-test (THR-C7), so absolute-count and
cap assertions are order-independent.
"""

from __future__ import annotations

import asyncio
import pathlib
from types import SimpleNamespace

import pytest

import app.services.llm as llm_mod
from app.agents import _degrade
from app.api import routes
from app.core.config import settings
from app.core.kernel import NyxKernel


def _fake_completion(content: str = "ok"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _scribe_snapshot():
    """A minimal, valid ScribeSnapshot for budget-threading assertions."""
    from app.schemas.book import ScribeSnapshot

    return ScribeSnapshot(
        thread_stamp="probe:1", epoch_index=1, epoch_name="The Hearth",
        covers_turns=(1, 3), boundary_turn=3,
        prose_window=["The door shuddered."], factual_chronicle=[], chronicle=[],
        life_voice="clipped", player_name="Wren", player_age=12,
        hamartia="Wrath", settlement="Ashfall", npc_names=["Maren"],
    )


# ---------------------------------------------------------------------------
# CHANGE 1 — bounded calls: config threaded to acompletion, on BOTH paths
# ---------------------------------------------------------------------------

class TestBoundedCalls:
    @pytest.mark.asyncio
    async def test_generate_threads_timeout_and_retries(self, monkeypatch):
        captured: dict = {}

        async def spy(**kwargs):
            captured.update(kwargs)
            return _fake_completion("ok")

        monkeypatch.setattr(llm_mod.litellm, "acompletion", spy)
        out = await llm_mod.generate(model="anthropic/claude-x", system_prompt="s", user_message="u")
        assert out == "ok"
        # THR-C3/C4: the correct kwarg is `timeout` (NOT the no-op `request_timeout`).
        assert captured.get("timeout") == settings.llm_request_timeout == 15.0
        assert captured.get("num_retries") == settings.llm_num_retries == 1
        assert "request_timeout" not in captured

    @pytest.mark.asyncio
    async def test_generate_honors_a_per_call_timeout_override(self, monkeypatch):
        # The write-behind escape hatch: long-form agents are NOT on the
        # sequential turn chain and must not inherit the interactive budget.
        captured: dict = {}

        async def spy(**kwargs):
            captured.update(kwargs)
            return _fake_completion("ok")

        monkeypatch.setattr(llm_mod.litellm, "acompletion", spy)
        await llm_mod.generate(
            model="anthropic/claude-x", system_prompt="s", user_message="u",
            timeout=settings.llm_longform_timeout,
        )
        assert captured.get("timeout") == settings.llm_longform_timeout
        assert settings.llm_longform_timeout > settings.llm_request_timeout

    @pytest.mark.asyncio
    async def test_writebehind_agents_use_the_longform_budget(self, monkeypatch):
        """Root cause of 'no life ever bound a book': a 2200-token chapter draft
        measures ~40s, but every real call was capped at the 15s interactive
        budget, so BOTH scribe attempts timed out and the book went unwritten.
        The Scribe and Morpheus must ask for the long-form wall clock."""
        import app.agents.morpheus as morpheus_mod
        import app.agents.scribe as scribe_mod

        seen: list[float | None] = []

        async def spy_generate(**kwargs):
            seen.append(kwargs.get("timeout"))
            raise RuntimeError("stop after capturing the budget")

        monkeypatch.setattr(scribe_mod.llm, "generate", spy_generate)
        monkeypatch.setattr(morpheus_mod.llm, "generate", spy_generate)
        monkeypatch.setattr(settings, "scribe_model", "anthropic/claude-x")
        monkeypatch.setattr(settings, "morpheus_model", "anthropic/claude-x")

        await scribe_mod.Scribe().draft_chapter(_scribe_snapshot())
        assert seen, "the Scribe never reached llm.generate"
        assert all(t == settings.llm_longform_timeout for t in seen), seen

    @pytest.mark.asyncio
    async def test_stream_threads_timeout_and_retries(self, monkeypatch):
        captured: dict = {}

        async def fake_stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"))])

        async def spy(**kwargs):
            captured.update(kwargs)
            return fake_stream()

        monkeypatch.setattr(llm_mod.litellm, "acompletion", spy)
        chunks = [c async for c in llm_mod.stream(model="anthropic/claude-x", system_prompt="s", user_message="u")]
        assert chunks == ["hi"]
        assert captured.get("timeout") == 15.0 and captured.get("num_retries") == 1
        assert "request_timeout" not in captured


# ---------------------------------------------------------------------------
# THR-C5 — the concurrency budget serializes but never self-deadlocks
# ---------------------------------------------------------------------------

class TestConcurrencyBudget:
    @pytest.mark.asyncio
    async def test_budget_below_fanout_serializes_without_hang(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_concurrency_budget", 2)
        llm_mod._BUDGET = None  # rebuild at the new size in this loop

        async def fake_acompletion(**kwargs):
            await asyncio.sleep(0.02)   # slow, but releases its slot on return
            return _fake_completion("ok")

        monkeypatch.setattr(llm_mod.litellm, "acompletion", fake_acompletion)

        async def one():
            return await llm_mod.generate(model="anthropic/x", system_prompt="s", user_message="u")

        # 3 concurrent real calls, budget 2 — must ALL complete (serialized), no hang.
        results = await asyncio.wait_for(asyncio.gather(one(), one(), one()), timeout=5.0)
        assert results == ["ok", "ok", "ok"]

    @pytest.mark.asyncio
    async def test_budget_exhaustion_raises_for_degrade(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_concurrency_budget", 1)
        monkeypatch.setattr(settings, "llm_acquire_timeout", 0.05)
        llm_mod._BUDGET = None
        sem = llm_mod._get_budget()
        await sem.acquire()  # hold the only slot
        try:
            with pytest.raises(TimeoutError):   # -> the agent degrades to mock, never blocks
                await llm_mod._acquire_budget()
        finally:
            sem.release()


# ---------------------------------------------------------------------------
# CHANGE 2 — visible degradation (structural coverage + discriminator)
# ---------------------------------------------------------------------------

class TestDegradation:
    def test_note_degraded_counts_and_logs(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            _degrade.note_degraded("clotho", "anthropic/x", RuntimeError("429"))
        assert _degrade.degraded_counts() == {"clotho": 1}
        assert any("AGENT DEGRADED" in r.getMessage() for r in caplog.records)

    def test_note_degraded_is_noop_in_mock(self):
        _degrade.note_degraded("clotho", "mock", RuntimeError("x"))
        assert _degrade.degraded_counts() == {}

    def test_coverage_is_structural_every_fallback_agent_calls_it(self):
        """THR-C1: each agent with a real-model -> mock fallback wires the helper.
        Guards against a new/missed except site shipping silently."""
        agents = pathlib.Path(__file__).resolve().parent.parent / "app" / "agents"
        expected = {
            "clotho", "lachesis", "eris", "nemesis", "atropos",
            "chronicler", "hypnos", "morpheus", "scribe", "sophia",
        }
        for name in sorted(expected):
            src = (agents / f"{name}.py").read_text(encoding="utf-8")
            assert "note_degraded(" in src, f"{name}.py has no note_degraded call"

    # -- isolation across ordering (THR-C7): two tests each force exactly one --
    def test_isolation_a(self):
        _degrade.note_degraded("alpha", "real", RuntimeError())
        assert _degrade.degraded_counts() == {"alpha": 1}

    def test_isolation_b(self):
        _degrade.note_degraded("beta", "real", RuntimeError())
        assert _degrade.degraded_counts() == {"beta": 1}

    @pytest.mark.asyncio
    async def test_full_mock_turn_never_degrades(self):
        k = NyxKernel()
        await k.initialize(
            hamartia="Unformed", player_id="thr", name="X", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        await k.process_turn("look around")
        assert _degrade.degraded_counts() == {}   # discriminator inert under the mock pin

    @pytest.mark.asyncio
    async def test_degraded_agent_does_not_wedge_the_turn(self, monkeypatch):
        """Soul re-assertion: a real-model agent that fails degrades to mock and
        is COUNTED, the turn still commits a deterministic consequence delta, and
        the thread continues — never a wedged turn (the always-continue invariant)."""
        monkeypatch.setattr(settings, "lachesis_model", "anthropic/claude-x")

        async def boom(*a, **k):
            raise RuntimeError("429 rate limited")

        monkeypatch.setattr(llm_mod, "generate", boom)

        k = NyxKernel()
        await k.initialize(
            hamartia="Unformed", player_id="thr", name="X", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        _degrade.reset_degraded()   # isolate the process_turn degrade from init
        result = await k.process_turn("help Sera with the harvest")
        assert result is not None                                   # turn completed, not wedged
        assert _degrade.degraded_counts().get("lachesis", 0) >= 1   # the collapse is visible
        assert result.state.soul_ledger.vectors is not None         # consequence math still ran


# ---------------------------------------------------------------------------
# THR-C6 — bounded sessions: LRU evicts idle, never an in-flight turn
# ---------------------------------------------------------------------------

class TestSessionCap:
    def test_lru_evicts_oldest_idle_over_cap(self, monkeypatch):
        import time

        monkeypatch.setattr(settings, "session_count_cap", 2)
        s1, _ = routes._get_or_create_session()
        s2, _ = routes._get_or_create_session()
        # Production sessions are seconds apart; in-test they tie at monotonic
        # resolution, so pin distinct (recent — not TTL-stale) activity times.
        now = time.monotonic()
        routes._sessions[s1].last_active = now - 10
        routes._sessions[s2].last_active = now - 5
        s3, _ = routes._get_or_create_session()   # overflow -> evict s1 (oldest idle)
        assert len(routes._sessions) == 2
        assert s1 not in routes._sessions
        assert s2 in routes._sessions and s3 in routes._sessions

    def test_lru_never_evicts_an_in_flight_session(self, monkeypatch):
        monkeypatch.setattr(settings, "session_count_cap", 2)
        s1, _ = routes._get_or_create_session()
        routes._sessions[s1].processing = 1        # s1 is the oldest, but mid-turn
        s2, _ = routes._get_or_create_session()
        s3, _ = routes._get_or_create_session()    # overflow -> must skip s1, evict s2
        assert s1 in routes._sessions              # protected despite being oldest
        assert s2 not in routes._sessions          # the oldest IDLE was evicted instead
        assert len(routes._sessions) == 2

    def test_all_busy_overflow_serves_rather_than_drops(self, monkeypatch):
        monkeypatch.setattr(settings, "session_count_cap", 1)
        s1, _ = routes._get_or_create_session()
        routes._sessions[s1].processing = 1
        s2, _ = routes._get_or_create_session()    # over cap, but s1 busy -> serve both
        routes._sessions[s2].processing = 1
        s3, _ = routes._get_or_create_session()    # all busy -> never drop a live turn
        assert s1 in routes._sessions and s2 in routes._sessions and s3 in routes._sessions
