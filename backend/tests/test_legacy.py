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
from app.services.legacy import augment_thread_summary, build_legacy_echo


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
    async def test_restart_loads_legacy_echo(self, configured_store, mock_models, monkeypatch):
        # Pin chaos off: an Eris miracle on the death turn would be flaky.
        import app.agents.eris as eris_module
        monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)

        first = NyxKernel()
        await first.initialize(
            hamartia="Unformed",
            player_id="echo_player",
            name="Hero",
            gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        await first.process_turn("I swear to protect Sera on my honor.")

        # Breaking the oath seals a 3-stage doom — death arrives staged,
        # not on the turn of the breaking.
        broken = await first.process_turn("I attack Sera with my knife.")
        assert broken.terminal is False
        assert first.state.doom.active
        assert first.state.doom.cause == "broken_oath"

        await first.process_turn("look around")
        death = await first.process_turn("wait")

        assert death.terminal is True
        assert "oath" in death.death_reason.lower()

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


class TestBuildLegacyEcho:
    """Direct unit coverage of the inheritance rules: which mark + pressure
    delta each ancestral flaw stamps on the next life, and the branch priority.

    The integration test above only exercises the oath path; these pin every
    branch so a refactor can't silently swap a bloodline's inherited mark.
    """

    def test_no_ancestor_returns_nothing(self):
        assert build_legacy_echo(None) == (None, {})
        assert build_legacy_echo({}) == (None, {})   # falsy dict — first life

    def test_default_is_ash_memory(self):
        # No oath in the death, no flaw match → the generic ancestral weight.
        echo, delta = build_legacy_echo(
            {"hamartia": "Unformed", "death_reason": "Old age took them.",
             "thread_id": "t1", "epitaph": "A quiet end."}
        )
        assert echo is not None
        assert echo.inherited_mark == "Ash Memory"
        assert delta == {"omen": 0.35}

    def test_oath_death_yields_oath_scar(self):
        echo, delta = build_legacy_echo(
            {"hamartia": "Unformed", "death_reason": "You broke a sacred oath."}
        )
        assert echo.inherited_mark == "Oath-Scar"
        assert delta == {"suspicion": 0.5}

    def test_oath_detected_in_epitaph_when_no_death_reason(self):
        # death_reason falls back to epitaph for the oath check (the _lower of
        # death_reason OR epitaph).
        echo, delta = build_legacy_echo(
            {"hamartia": "Wrath of the Untempered",
             "epitaph": "Here lies one who broke their oath."}
        )
        assert echo.inherited_mark == "Oath-Scar"   # oath wins even over wrath
        assert delta == {"suspicion": 0.5}

    def test_wrath_yields_battle_scar(self):
        echo, delta = build_legacy_echo({"hamartia": "Wrath of the Untempered"})
        assert echo.inherited_mark == "Battle Scar"
        assert delta == {"wounds": 0.4}

    @pytest.mark.parametrize("flaw", ["Hubris of the Intellect", "Pride That Blinds",
                                      "Vainglory", "Avarice Unbound"])
    def test_proud_bloodlines_yield_crowds_memory(self, flaw):
        echo, delta = build_legacy_echo({"hamartia": flaw})
        assert echo.inherited_mark == "Crowd's Memory"
        assert delta == {"suspicion": 0.3, "faction_heat": 0.25}

    def test_cowardice_yields_whisper_of_shame(self):
        echo, delta = build_legacy_echo({"hamartia": "Cowardice Veiled as Wisdom"})
        assert echo.inherited_mark == "Whisper of Shame"
        assert delta == {"faction_heat": 0.4}

    def test_oath_takes_priority_over_the_flaw_mark(self):
        # An oath-breaker who was ALSO wrathful is remembered for the broken
        # vow, not the wrath — the death dominates the inherited mark.
        echo, delta = build_legacy_echo(
            {"hamartia": "Wrath of the Untempered",
             "death_reason": "You broke your oath in a rage."}
        )
        assert echo.inherited_mark == "Oath-Scar"
        assert delta == {"suspicion": 0.5}

    def test_echo_carries_identity_with_fallbacks(self):
        echo, _ = build_legacy_echo(
            {"hamartia": "Pride That Blinds", "source_thread_id": "anc-9"}
        )
        assert echo.source_thread_id == "anc-9"   # thread_id → source_thread_id fallback
        assert echo.epitaph == "A thread lost to silence."   # missing-epitaph fallback
        assert echo.hamartia == "Pride That Blinds"


class TestAugmentThreadSummary:
    """The title-screen summary fields derived from a dead thread."""

    def test_with_echo_attaches_mark_and_effect_and_preserves_fields(self):
        summary = augment_thread_summary(
            {"hamartia": "Wrath of the Untempered", "name": "Edric", "thread_id": "t7"}
        )
        assert summary["legacy_mark"] == "Battle Scar"
        assert summary["legacy_effect"].startswith("Wounds begin slightly higher")
        assert summary["name"] == "Edric"      # original fields preserved
        assert summary["thread_id"] == "t7"

    def test_without_echo_sets_empty_legacy_fields(self):
        # An empty/falsy thread yields no echo → blank legacy fields, no crash.
        summary = augment_thread_summary({})
        assert summary["legacy_mark"] == ""
        assert summary["legacy_effect"] == ""
