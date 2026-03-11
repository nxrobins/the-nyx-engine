"""Shared fixtures for the Nyx Engine test suite.

Provides factories for ThreadState, SoulVectors, and agent responses
so tests stay concise and don't repeat construction boilerplate.
"""

from __future__ import annotations

import pytest

from app.schemas.state import (
    AtroposResponse,
    ChroniclerResponse,
    ErisResponse,
    LachesisResponse,
    MomusValidation,
    NemesisResponse,
    Oath,
    SessionData,
    SoulLedger,
    SoulVectors,
    TheLoom,
    ThreadState,
    TurnResult,
)


# ---------------------------------------------------------------------------
# Soul Vectors
# ---------------------------------------------------------------------------

@pytest.fixture
def default_vectors() -> SoulVectors:
    """All vectors at 5.0 — perfectly balanced soul."""
    return SoulVectors()


@pytest.fixture
def bia_dominant_vectors() -> SoulVectors:
    """Bia at 9.0 — a soul consumed by violence."""
    return SoulVectors(metis=3.0, bia=9.0, kleos=4.0, aidos=2.0)


@pytest.fixture
def dead_soul_vectors() -> SoulVectors:
    """All vectors collapsed to ≤ 1.0 — dead soul trigger."""
    return SoulVectors(metis=0.5, bia=1.0, kleos=0.0, aidos=0.8)


@pytest.fixture
def milestone_vectors() -> SoulVectors:
    """Metis at 10.0 — milestone trigger."""
    return SoulVectors(metis=10.0, bia=5.0, kleos=5.0, aidos=5.0)


# ---------------------------------------------------------------------------
# Thread State
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_state() -> ThreadState:
    """A brand-new ThreadState with defaults — Turn 0, balanced soul."""
    return ThreadState()


@pytest.fixture
def mid_game_state() -> ThreadState:
    """Turn 5, Phase 2, some history — a typical mid-game state."""
    return ThreadState(
        session=SessionData(
            player_id="test_player",
            player_name="Achilles",
            player_gender="boy",
            turn_count=5,
            run_number=1,
            epoch_phase=2,
            ui_mode="buttons",
            current_environment="A blood-soaked arena under a bruised sky.",
        ),
        soul_ledger=SoulLedger(
            hamartia="Wrath of the Untempered",
            vectors=SoulVectors(metis=4.0, bia=7.5, kleos=6.0, aidos=3.0),
            active_oaths=[
                Oath(
                    oath_id="oath_001",
                    text="I swear to avenge my fallen brother.",
                    turn_sworn=3,
                ),
            ],
        ),
        the_loom=TheLoom(
            current_prophecy="The blade you sharpen will one day find your own throat.",
        ),
        last_action="strike the merchant",
        last_outcome="violent_triumph",
        rag_context=[
            "Turn 3: Player swore oath of vengeance.",
            "Turn 4: Player attacked a guard in the market.",
        ],
    )


@pytest.fixture
def unformed_turn10_state() -> ThreadState:
    """Turn 10, epoch_phase 4, hamartia still 'Unformed' — for hamartia fork tests."""
    return ThreadState(
        session=SessionData(
            player_id="test_player",
            player_name="Orpheus",
            player_gender="boy",
            turn_count=10,
            epoch_phase=4,
            ui_mode="open",
            current_environment="A crossroads beneath a starless sky.",
        ),
        soul_ledger=SoulLedger(
            hamartia="Unformed",
            vectors=SoulVectors(metis=8.0, bia=4.0, kleos=5.0, aidos=3.0),
        ),
        the_loom=TheLoom(
            current_prophecy="The thread awaits its true color.",
        ),
    )


# ---------------------------------------------------------------------------
# Agent Response Factories
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_lachesis() -> LachesisResponse:
    """A clean, valid Lachesis response with modest bia deltas."""
    return LachesisResponse(
        valid_action=True,
        vector_deltas={"bia": 2.0, "aidos": -0.5},
        environment_update="The arena echoes with the clash of iron.",
    )


@pytest.fixture
def invalid_lachesis() -> LachesisResponse:
    """Lachesis blocks the action — impossible."""
    return LachesisResponse(
        valid_action=False,
        reason="Action exceeds mortal capabilities.",
    )


@pytest.fixture
def terminal_atropos() -> AtroposResponse:
    """Atropos severs the thread — player is dead."""
    return AtroposResponse(
        terminal_state=True,
        death_reason="The void swallowed what remained.",
    )


@pytest.fixture
def alive_atropos() -> AtroposResponse:
    """Atropos allows the thread to continue."""
    return AtroposResponse(terminal_state=False)


@pytest.fixture
def nemesis_punishment() -> NemesisResponse:
    """Nemesis intervenes with punishment."""
    return NemesisResponse(
        intervene=True,
        intervention_type="punishment",
        updated_prophecy="The scales tip. Your reckoning approaches.",
        punishment_description="A searing brand appears on your forearm — the mark of Nemesis.",
        vector_penalty={"bia": -2.0, "kleos": -1.0},
    )


@pytest.fixture
def nemesis_lethal() -> NemesisResponse:
    """Nemesis intervenes with lethal punishment."""
    return NemesisResponse(
        intervene=True,
        intervention_type="lethal_punishment",
        updated_prophecy="The blade falls.",
        punishment_description="Nemesis strikes. Your oath is shattered.",
        vector_penalty={"bia": -3.0},
    )


@pytest.fixture
def nemesis_silent() -> NemesisResponse:
    """Nemesis does not intervene."""
    return NemesisResponse(intervene=False)


@pytest.fixture
def eris_chaos() -> ErisResponse:
    """Eris injects chaos."""
    return ErisResponse(
        chaos_triggered=True,
        chaos_description="The ground cracks open. Laughter echoes from below.",
        chaos_severity=0.7,
        vector_chaos={"metis": 1.5, "aidos": -1.0},
    )


@pytest.fixture
def eris_silent() -> ErisResponse:
    """Eris does not trigger."""
    return ErisResponse(chaos_triggered=False)
