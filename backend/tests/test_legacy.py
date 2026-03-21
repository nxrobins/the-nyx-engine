"""Tests for Phase 3 legacy echoes and default local persistence."""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.db import (
    close_pool,
    create_thread,
    create_turn,
    ensure_player,
    get_dead_threads,
    get_last_ancestor,
    init_pool,
    update_thread_death,
)


@pytest.fixture
async def configured_store(monkeypatch, tmp_path):
    from app.core.config import settings

    await close_pool()
    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_store_path", str(tmp_path / "nyx-test.sqlite3"))
    await init_pool()
    yield
    await close_pool()


@pytest.fixture
def mock_models(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "clotho_model", "mock")
    monkeypatch.setattr(settings, "lachesis_model", "mock")
    monkeypatch.setattr(settings, "nemesis_model", "mock")
    monkeypatch.setattr(settings, "eris_model", "mock")
    monkeypatch.setattr(settings, "eris_chaos_probability", 0.0)
    monkeypatch.setattr(settings, "hypnos_model", "mock")
    monkeypatch.setattr(settings, "chronicler_model", "mock")


class TestSQLitePersistence:
    """Runs should persist locally even without PostgreSQL."""

    @pytest.mark.asyncio
    async def test_dead_thread_round_trips_through_sqlite(self, configured_store):
        await ensure_player("legacy_player")
        thread_id = await create_thread("legacy_player", "Wrath")
        assert thread_id is not None

        await create_turn(
            thread_id=thread_id,
            turn_number=1,
            action="attack",
            outcome="combat",
            prose_summary="A violent turn.",
            soul_vectors={"metis": 3.0, "bia": 8.0, "kleos": 4.0, "aidos": 2.0},
        )
        await update_thread_death(
            thread_id,
            "Here fell one who broke faith.",
            2,
            death_reason="You broke a sacred oath.",
            final_soul_vectors={"metis": 1.0, "bia": 1.0, "kleos": 1.0, "aidos": 1.0},
        )

        threads = await get_dead_threads("legacy_player")
        ancestor = await get_last_ancestor("legacy_player")

        assert len(threads) == 1
        assert threads[0]["death_reason"] == "You broke a sacred oath."
        assert ancestor is not None
        assert ancestor["thread_id"] == thread_id


class TestLegacyEchoes:
    """A dead run should leave a mechanical and narrative mark on the next life."""

    @pytest.mark.asyncio
    async def test_restart_loads_legacy_echo(self, configured_store, mock_models):
        first = NyxKernel()
        await first.initialize(
            hamartia="Unformed",
            player_id="echo_player",
            name="Hero",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        await first.process_turn("I swear to protect Sera on my honor.")
        death = await first.process_turn("I attack Sera with my knife.")

        assert death.terminal is True

        second = NyxKernel()
        rebirth = await second.initialize(
            hamartia="Unformed",
            player_id="echo_player",
            name="Heir",
            gender="girl",
            first_memory="A crowd shouting a name that was not mine.",
        )

        assert rebirth.state.legacy_echoes
        assert rebirth.state.legacy_echoes[0].inherited_mark == "Oath-Scar"
        assert rebirth.state.pressures.suspicion >= 0.5
