"""Kernel ↔ Morpheus integration — fire, harvest, consume, fall back.

Pins the P2 lifecycle through the real pipeline in mock mode:
the authored beat is a ceiling over the floor, validated at the moment
of use, and every failure mode degrades to exactly the game that
existed before Morpheus.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.kernel import NyxKernel
from app.schemas.morpheus import (
    AuthoredBeat,
    BeatPrecondition,
    BeatSheet,
    LedgerUpdates,
    Promise,
)


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _init(kernel: NyxKernel) -> None:
    await kernel.initialize(
        hamartia="Unformed",
        player_id="morpheus_test",
        name="Iris",
        gender="girl",
        first_memory="The weight of a heavy stone in my hand.",  # Ashfall: Maren, Kael
    )
    # THE PULSE calibration: birth is turn 0 — the breath is every life's
    # first action, restoring this file's original turn frame (init -> turn 1).
    await kernel.process_turn("Draw your first breath.")


async def _to_adulthood(kernel: NyxKernel) -> None:
    """Play childhood + the Fork, landing the thread in adulthood (phase 4)."""
    await _init(kernel)
    for _ in range(8):
        await kernel.process_turn("look around")
    await kernel.process_turn("I take up my tools and choose my road")  # the Fork
    assert kernel.state.session.epoch_phase == 4


async def _adult_crucible(kernel: NyxKernel, action: str) -> None:
    """Force ONE adult full-pipeline turn (a crucible — which closes a chapter).

    Clearing pending_vignette is how the suite forces the crucible path; an
    armed vignette would take the cheap path, which never builds a TurnContext.
    """
    kernel.state.pending_vignette = None
    await kernel.process_turn(action)


async def _play_to_boundary(kernel: NyxKernel) -> None:
    """Turns 2 and 3 — ends on the epoch-1 RESOLUTION, firing Morpheus."""
    await kernel.process_turn("hide behind the ore carts")
    await kernel.process_turn("hide the black stone in my bedroll")
    await asyncio.sleep(0)  # let the mock task run to completion


class TestTheRealignment:
    """V2-H1: the organs must fire on the CHAPTER, not a turn-modulo beat label.

    THE PULSE made the chapter the narrative unit — in adulthood every
    full-pipeline turn is a crucible, and a crucible always closes its chapter.
    But the organs gated on `beat_position == "RESOLUTION"`, which
    `select_adult_beat` derives from `(turn - 10) % 3` — a raw-turn cycle that
    vignettes push out of step. So they fired on ~1 adult chapter close in 3,
    chosen by however many vignettes happened to intervene: Morpheus sheets
    stale-dropped (the Ledger died in adulthood) and the Scribe starved.
    """

    @pytest.mark.asyncio
    async def test_every_adult_chapter_close_fires_both_organs(self, kernel):
        await _to_adulthood(kernel)
        fired: list[tuple[int, str, bool, bool]] = []
        for i in range(3):
            kernel._morpheus_task = None
            kernel._scribe_task = None
            chapters_before = kernel.state.session.chapter_index
            await _adult_crucible(kernel, f"I press on through the day {i}")
            # Each of these turns really did close a chapter...
            assert kernel.state.session.chapter_index == chapters_before + 1
            fired.append((
                kernel.state.session.turn_count,
                kernel.state.session.beat_position,
                kernel._morpheus_task is not None,
                kernel._scribe_task is not None,
            ))
        # ...so the Author and the biographer must have been fired at EVERY one,
        # whatever act label the beat happened to carry.
        assert all(m for *_, m, _ in fired), fired
        assert all(s for *_, _, s in fired), fired

    @pytest.mark.asyncio
    async def test_an_adult_sheet_survives_the_vignettes_of_its_chapter(self, kernel):
        """P1-C6: the floor-beat window is the scheduler's NEXT CHAPTER, not 3
        raw turns. An adult chapter runs up to 6 turns (5 vignettes + its
        crucible), and only the crucible consumes an authored beat — so a
        3-raw-turn window expires before the chapter it was authored FOR is
        ever played. That is why every adult sheet stale-dropped."""
        await _to_adulthood(kernel)
        session = kernel.state.session
        boundary = session.turn_count

        kernel._beat_sheet = BeatSheet(
            sheet_version=1,
            thread_stamp=f"{session.player_id}:{session.run_number}",
            epoch_start_turn=boundary + 1,      # authored for the chapter now opening
            based_on_turn=boundary,
            beats=[AuthoredBeat(position="SETUP", directive="NEW SCENE. Maren " + "x" * 50)],
        )
        kernel._sheet_chapter = session.chapter_index + 1

        # Four vignettes are lived, then the chapter's crucible finally lands.
        session.turn_count = boundary + 5
        session.chapter_index += 1               # we are IN the chapter it serves
        directive, _ = kernel._authored_directive(session.turn_count, "SETUP")
        assert directive, "the authored beat expired before its own chapter was played"

    @pytest.mark.asyncio
    async def test_a_sheet_from_a_previous_chapter_is_still_dropped(self, kernel):
        # The counterpart: widening the window to the chapter must not widen it
        # to forever. A plan for a chapter already lived is stale and the floor
        # must play — otherwise the realignment just removes the guard.
        await _to_adulthood(kernel)
        session = kernel.state.session
        kernel._beat_sheet = BeatSheet(
            sheet_version=1,
            thread_stamp=f"{session.player_id}:{session.run_number}",
            epoch_start_turn=session.turn_count + 1,
            based_on_turn=session.turn_count,
            beats=[AuthoredBeat(position="SETUP", directive="NEW SCENE. Maren " + "x" * 50)],
        )
        kernel._sheet_chapter = session.chapter_index      # serves THIS chapter
        session.chapter_index += 1                          # ...which has now closed
        directive, _ = kernel._authored_directive(session.turn_count, "SETUP")
        assert directive == "", "a plan for a lived chapter must not still play"

    @pytest.mark.asyncio
    async def test_an_in_flight_organ_survives_the_next_chapter_close(self, kernel):
        """Backpressure. Firing at EVERY close means the next close can arrive
        before a 25-40s organ finishes (a 2-turn chapter, or a doom — which
        forces a crucible every turn). Cancel-and-refire would restart the
        Author forever and it would never once complete."""
        await _to_adulthood(kernel)

        async def _slow_reoutline(snapshot):
            await asyncio.sleep(30)   # still running when the next chapter closes
            return None

        kernel.morpheus.reoutline = _slow_reoutline
        await _adult_crucible(kernel, "the first close")
        first = kernel._morpheus_task
        assert first is not None and not first.done()

        await _adult_crucible(kernel, "the second close")
        assert kernel._morpheus_task is first, "the in-flight Author was restarted"
        assert not first.cancelled()
        first.cancel()   # tidy up the parked task


class TestFireAndHarvest:
    @pytest.mark.asyncio
    async def test_resolution_fires_morpheus(self, kernel):
        await _init(kernel)
        await kernel.process_turn("hide behind the ore carts")
        assert kernel._morpheus_task is None  # COMPLICATION: no fire
        await kernel.process_turn("hide the black stone")
        assert kernel._morpheus_task is not None  # RESOLUTION: fired

    @pytest.mark.asyncio
    async def test_next_turn_harvests_sheet_and_plants(self, kernel):
        await _init(kernel)
        await _play_to_boundary(kernel)
        await kernel.process_turn("follow Maren to the sorting pile")  # turn 4
        assert kernel._beat_sheet is not None
        assert kernel._beat_sheet.epoch_start_turn == 4
        # The mock noticed a plant citing the lived boundary turn.
        assert len(kernel.state.ledger) == 1
        plant = kernel.state.ledger[0]
        assert plant.event_turn == 3
        assert plant.status == "planted"
        assert "hide the black stone" in plant.description

    @pytest.mark.asyncio
    async def test_authored_directive_reaches_clotho(self, kernel, monkeypatch):
        await _init(kernel)
        await _play_to_boundary(kernel)

        captured: list[str] = []
        original = kernel.clotho.evaluate

        async def spy(state, action, **kwargs):
            captured.append(kwargs.get("vignette_directive", ""))
            return await original(state, action, **kwargs)

        monkeypatch.setattr(kernel.clotho, "evaluate", spy)
        await kernel.process_turn("follow Maren")  # turn 4 SETUP
        # The mock sheet grounds beats with a living NPC's name.
        assert captured and "NEW SCENE" in captured[0]
        assert any(name in captured[0] for name in ("Maren", "Kael"))


class TestPaymentAndAudit:
    @pytest.mark.asyncio
    async def test_due_promise_paid_by_authored_resolution(self, kernel):
        await _init(kernel)
        # Seed a promise BEFORE the boundary so the fired snapshot carries it.
        kernel.state.ledger.append(
            Promise(
                promise_id="p-debt",
                description="The lamp borrowed from the widow",
                event_turn=1,
                due_turn=6,
            )
        )
        await _play_to_boundary(kernel)            # fires with p-debt active
        await kernel.process_turn("work the pile")  # 4: harvest
        await kernel.process_turn("ask Kael about the lamp")  # 5
        await kernel.process_turn("return the lamp")          # 6: RESOLUTION pays
        debt = next(p for p in kernel.state.ledger if p.promise_id == "p-debt")
        assert debt.status == "paid"
        assert debt.paid_turn == 6

    @pytest.mark.asyncio
    async def test_unpaid_promise_abandons_and_omen_rises(self, kernel):
        await _init(kernel)
        kernel.state.ledger.append(
            Promise(
                promise_id="p-late",
                description="The promise nobody kept",
                event_turn=1,
                due_turn=3,
            )
        )
        omen_before = kernel.state.pressures.omen
        await kernel.process_turn("hide behind the carts")   # turn 2: window open
        await kernel.process_turn("wait in the dark")        # turn 3: closes (due 3)
        await kernel.process_turn("keep waiting")            # turn 4: past due → abandoned
        late = next(p for p in kernel.state.ledger if p.promise_id == "p-late")
        assert late.status == "abandoned"
        assert kernel.state.pressures.omen > omen_before


class TestValidateOnConsume:
    @pytest.mark.asyncio
    async def test_stale_stamp_dropped_at_harvest(self, kernel, monkeypatch):
        await _init(kernel)

        async def wrong_thread(snapshot):
            return BeatSheet(
                sheet_version=1,
                thread_stamp="someone_else:9",
                epoch_start_turn=snapshot.epoch_start_turn,
                based_on_turn=snapshot.boundary_turn,
                beats=[AuthoredBeat(position="SETUP", directive="NEW SCENE. Maren " + "x" * 50)],
            )

        monkeypatch.setattr(kernel.morpheus, "reoutline", wrong_thread)
        await _play_to_boundary(kernel)
        await kernel.process_turn("look around")
        assert kernel._beat_sheet is None  # dropped; floor played

    @pytest.mark.asyncio
    async def test_mystical_beat_dropped_by_gate(self, kernel, monkeypatch):
        await _init(kernel)

        async def mystical(snapshot):
            return BeatSheet(
                sheet_version=1,
                thread_stamp=snapshot.thread_stamp,
                epoch_start_turn=snapshot.epoch_start_turn,
                based_on_turn=snapshot.boundary_turn,
                beats=[
                    AuthoredBeat(
                        position="SETUP",
                        directive=(
                            "NEW SCENE. Maren watches the fabric of reality "
                            "shiver above the threshold between worlds tonight."
                        ),
                    )
                ],
            )

        monkeypatch.setattr(kernel.morpheus, "reoutline", mystical)
        await _play_to_boundary(kernel)
        await kernel.process_turn("look around")
        assert kernel._beat_sheet is None  # all beats failed the gate

    @pytest.mark.asyncio
    async def test_dead_precondition_falls_back_to_floor(self, kernel, monkeypatch):
        """Harvest passes while Maren lives; she dies before the COMPLICATION
        beat is consumed — validate-at-the-moment-of-use drops that one beat."""
        await _init(kernel)
        marker = "THE AUTHORED BEAT PLAYS"

        async def conditional(snapshot):
            return BeatSheet(
                sheet_version=1,
                thread_stamp=snapshot.thread_stamp,
                epoch_start_turn=snapshot.epoch_start_turn,
                based_on_turn=snapshot.boundary_turn,
                beats=[
                    AuthoredBeat(
                        position="SETUP",
                        directive="NEW SCENE. Maren kneels by the lamp, counting the ore tokens twice.",
                    ),
                    AuthoredBeat(
                        position="COMPLICATION",
                        directive=f"NEW SCENE. Maren bars the door. {marker}." + " x" * 20,
                        preconditions=BeatPrecondition(npcs_alive=["Maren"]),
                    ),
                ],
            )

        monkeypatch.setattr(kernel.morpheus, "reoutline", conditional)
        await _play_to_boundary(kernel)

        captured: list[str] = []
        original = kernel.clotho.evaluate

        async def spy(state, action, **kwargs):
            captured.append(kwargs.get("vignette_directive", ""))
            return await original(state, action, **kwargs)

        monkeypatch.setattr(kernel.clotho, "evaluate", spy)

        await kernel.process_turn("look around")   # turn 4: harvest (Maren alive) + SETUP
        assert kernel._beat_sheet is not None
        assert len(kernel._beat_sheet.beats) == 2  # both survived the harvest gate

        # Maren dies between harvest and the next beat's consumption.
        for npc in kernel.state.canon.npcs.values():
            if npc.name == "Maren":
                npc.status = "dead"

        await kernel.process_turn("listen at the door")  # turn 5: COMPLICATION
        assert len(captured) == 2
        assert marker not in captured[1]  # precondition failed → floor played


class TestLifecycleCleanup:
    @pytest.mark.asyncio
    async def test_reset_cancels_and_clears(self, kernel):
        await _init(kernel)
        await _play_to_boundary(kernel)
        await kernel.process_turn("look around")
        assert kernel._beat_sheet is not None
        kernel.reset()
        assert kernel._beat_sheet is None
        assert kernel._morpheus_task is None
        assert kernel.state.ledger == []

    @pytest.mark.asyncio
    async def test_dream_reads_the_ledger(self, kernel):
        await _init(kernel)
        await _play_to_boundary(kernel)
        await kernel.process_turn("work the pile")   # 4 (harvest plants p-t3)
        await kernel.process_turn("ask Kael")        # 5
        await kernel.process_turn("say nothing")     # 6: RESOLUTION → dream
        assert "You dream of it again" in kernel.state.current_dream
