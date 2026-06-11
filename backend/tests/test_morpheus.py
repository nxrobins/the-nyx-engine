"""Morpheus Re-Outliner tests — mock determinism and contract discipline."""

from __future__ import annotations

import pytest

from app.agents.morpheus import Morpheus, _parse_sheet_payload
from app.schemas.morpheus import FloorBeat, MorpheusSnapshot, Promise


def _snapshot(**overrides) -> MorpheusSnapshot:
    payload = dict(
        thread_stamp="test:1",
        boundary_turn=3,
        epoch_start_turn=4,
        prose_window=["The shaft breathed cold.", "Kael said nothing at supper."],
        factual_chronicle=["Turn 3: the player hid the black stone from Torval."],
        chronicle=["The Child learned that silence has teeth."],
        last_action="hide the black stone in the bedroll",
        soul_summary="metis 6.0 | bia 5.0 | kleos 4.5 | aidos 7.0 — hamartia Unformed",
        pressure_summary="suspicion 1.2: people are watching",
        npc_names_alive=["Maren", "Kael"],
        clock_lines=["clock_ashfall_pressure|The shaft stays blocked|1/4"],
        active_promises=[],
        floor_beats=[
            FloorBeat(turn=4, position="SETUP", directive="NEW SCENE. Years have passed. Maren works the sorting pile."),
            FloorBeat(turn=5, position="COMPLICATION", directive="NEW SCENE. Time has passed. A friend demands loyalty from Kael's son."),
            FloorBeat(turn=6, position="RESOLUTION", directive="NEW SCENE. The social conflict reaches a crisis before Maren."),
        ],
    )
    payload.update(overrides)
    return MorpheusSnapshot(**payload)


class TestMockSheet:
    @pytest.mark.asyncio
    async def test_mock_returns_valid_stamped_sheet(self):
        sheet = await Morpheus().reoutline(_snapshot())
        assert sheet is not None
        assert sheet.thread_stamp == "test:1"
        assert sheet.based_on_turn == 3
        assert sheet.epoch_start_turn == 4
        assert {b.position for b in sheet.beats} == {"SETUP", "COMPLICATION", "RESOLUTION"}

    @pytest.mark.asyncio
    async def test_mock_is_deterministic(self):
        a = await Morpheus().reoutline(_snapshot())
        b = await Morpheus().reoutline(_snapshot())
        assert a == b

    @pytest.mark.asyncio
    async def test_mock_plants_a_cited_promise(self):
        sheet = await Morpheus().reoutline(_snapshot())
        plants = sheet.ledger_updates.new_plants
        assert len(plants) == 1
        assert plants[0].event_turn == 3          # cites the lived boundary
        assert "hide the black stone" in plants[0].description

    @pytest.mark.asyncio
    async def test_mock_pays_due_promise_on_resolution(self):
        due = Promise(
            promise_id="p-old",
            description="The stone Torval never found",
            event_turn=2,
            due_turn=6,
        )
        sheet = await Morpheus().reoutline(_snapshot(active_promises=[due]))
        resolution = sheet.beat_for("RESOLUTION")
        assert "p-old" in resolution.pays_promise_ids
        assert "THE LOOM REMEMBERS" in resolution.directive

    @pytest.mark.asyncio
    async def test_mock_beats_keep_scene_isolation(self):
        sheet = await Morpheus().reoutline(_snapshot())
        assert all(b.directive.lstrip().startswith("NEW SCENE") for b in sheet.beats)


class TestParsePayload:
    def test_plain_json(self):
        assert _parse_sheet_payload('{"beats": []}') == {"beats": []}

    def test_fenced_json(self):
        assert _parse_sheet_payload('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_wrapped_json(self):
        assert _parse_sheet_payload('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _parse_sheet_payload("I cannot author beats today.")


class TestRealModeFailure:
    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "morpheus_model", "anthropic/whatever")

        async def boom(**kwargs):
            raise RuntimeError("no network in tests")

        import app.agents.morpheus as morpheus_module
        monkeypatch.setattr(morpheus_module.llm, "generate", boom)

        sheet = await Morpheus().reoutline(_snapshot())
        assert sheet is None  # the floor plays
