"""The vignette turn path (THE PULSE, sub-slice 3 — P1-C4/C8).

The cheap beat through the real kernel: packet applied deterministically, no
council convened (architecture-style: the lethal/judgment agents are booby-
trapped and must never fire), finalize-lite persists, receipts land, escalation
sends non-button input to the full pipeline, and chapters close with age.
"""

from __future__ import annotations

import json

import pytest

from app.core.kernel import NyxKernel
from app.schemas.vignette import BoundVignette, ConsequencePacket, VignetteChoice


@pytest.fixture
def kernel() -> NyxKernel:
    return NyxKernel()


async def _adult_kernel(k: NyxKernel) -> None:
    """Initialize and play through childhood + the Fork into adulthood."""
    await k.initialize(
        hamartia="Unformed", player_id="p", name="Hero", gender="boy",
        first_memory="The weight of a heavy stone in my hand.",
    )
    for _ in range(9):
        await k.process_turn("look around")
    await k.process_turn("I take up my tools and choose my road")  # the Fork


def _arm(k: NyxKernel, *, evolution: str = "The scale is watched now.") -> BoundVignette:
    """Arm a known pending vignette directly (unit-grain control)."""
    bound = BoundVignette(
        vignette_id="test_beat",
        situation="The weigh-master's scale reads light again.",
        choices=[
            VignetteChoice(label="Demand a true weigh", packet=ConsequencePacket(
                vector_deltas={"bia": 0.8}, pressure_deltas={"faction_heat": 0.4},
                scene_evolution=evolution,
            )),
            VignetteChoice(label="Mark your carts secretly", packet=ConsequencePacket(
                vector_deltas={"metis": 0.8},
            )),
            VignetteChoice(label="Keep your head down", packet=ConsequencePacket(
                vector_deltas={"aidos": 0.6},
            )),
        ],
    )
    k.state.pending_vignette = bound
    k.state.session.ui_mode = "buttons"
    return bound


def _boobytrap_council(k: NyxKernel):
    """The lethal grain lives at crucibles (P1-C4): none of these may run."""
    async def _bang(*a, **kw):
        raise AssertionError("council agent invoked on a vignette beat")
    k.lachesis.evaluate = _bang
    k.nemesis.evaluate = _bang
    k.eris.evaluate = _bang
    k.atropos.evaluate = _bang
    k.momus.validate_prose = _bang
    k.sophia.judge = _bang if hasattr(k.sophia, "judge") else k.sophia.evaluate


class TestVignetteTurn:
    @pytest.mark.asyncio
    async def test_packet_applies_and_no_council_convenes(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        _boobytrap_council(kernel)
        bia_before = kernel.state.soul_ledger.vectors.bia
        heat_before = kernel.state.pressures.faction_heat
        turn_before = kernel.state.session.turn_count

        result = await kernel.process_turn("Demand a true weigh")

        assert kernel.state.session.turn_count == turn_before + 1
        assert kernel.state.soul_ledger.vectors.bia == pytest.approx(min(10.0, bia_before + 0.8))
        assert kernel.state.pressures.faction_heat == pytest.approx(min(10.0, heat_before + 0.4))
        assert result.terminal is False
        # The evolution moved the scene problem (the stasis-killer).
        assert kernel.state.canon.current_scene.immediate_problem == "The scale is watched now."

    @pytest.mark.asyncio
    async def test_receipt_lands_in_the_trace(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        await kernel.process_turn("Mark your carts secretly")
        trace = kernel.state.recent_traces[-1]
        assert trace.winner_order == ["vignette"]
        assert "test_beat" in trace.final_reason
        assert "metis" in trace.final_reason  # the packet is the receipt

    @pytest.mark.asyncio
    async def test_finalize_lite_bookkeeping(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        beats_before = kernel.state.session.beats_spent
        await kernel.process_turn("Keep your head down")
        s = kernel.state
        assert "test_beat" in s.used_vignette_ids          # no-repeat ledger
        assert s.session.beats_spent == beats_before + 1   # budget spent
        assert s.session.beat_kind == "vignette"
        assert s.last_outcome == "vignette"
        assert s.prose_history[-1].startswith("The weigh-master's scale")

    @pytest.mark.asyncio
    async def test_non_button_input_escalates_to_the_council(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        turn_before = kernel.state.session.turn_count
        result = await kernel.process_turn("I burn the weigh-house to the ground")
        # Escalated: the OLD pending is gone (a new one may be legitimately
        # armed by the crucible's own scheduling), the FULL pipeline ran (turn
        # advanced, a real council trace — not a vignette receipt).
        pending = kernel.state.pending_vignette
        assert pending is None or pending.vignette_id != "test_beat"
        assert kernel.state.session.turn_count == turn_before + 1
        assert kernel.state.recent_traces[-1].winner_order != ["vignette"]
        assert result is not None


class TestVignetteAtomicity:
    """V2-H4: the cheap turn mutates self.state before rendering; a failure must
    fully revert it, so a retry re-applies the packet exactly once, and an
    invalid free-text escalation must not destroy the armed vignette."""

    @pytest.mark.asyncio
    async def test_render_failure_fully_reverts_then_retry_applies_once(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel, evolution="The scale is watched now.")
        turn_before = kernel.state.session.turn_count
        bia_before = kernel.state.soul_ledger.vectors.bia
        used_before = list(kernel.state.used_vignette_ids)

        original = kernel.clotho.render_vignette

        async def _boom(*a, **k):
            raise RuntimeError("render died mid-turn")

        kernel.clotho.render_vignette = _boom
        with pytest.raises(RuntimeError):
            await kernel.process_turn("Demand a true weigh")

        # Fully reverted — the cheap turn never happened.
        assert kernel.state.session.turn_count == turn_before
        assert kernel.state.soul_ledger.vectors.bia == bia_before
        assert kernel.state.used_vignette_ids == used_before
        assert kernel.state.pending_vignette is not None
        assert kernel.state.pending_vignette.vignette_id == "test_beat"

        # A retry applies the packet EXACTLY ONCE (no double-apply).
        kernel.clotho.render_vignette = original
        await kernel.process_turn("Demand a true weigh")
        assert kernel.state.session.turn_count == turn_before + 1
        assert kernel.state.soul_ledger.vectors.bia == pytest.approx(min(10.0, bia_before + 0.8))

    @pytest.mark.asyncio
    async def test_stream_render_failure_reverts(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        turn_before = kernel.state.session.turn_count
        bia_before = kernel.state.soul_ledger.vectors.bia

        async def _boom_stream(*a, **k):
            yield "the scale groans"      # a token lands...
            raise RuntimeError("stream died")  # ...then the connection dies

        kernel.clotho.render_vignette_stream = _boom_stream
        with pytest.raises(RuntimeError):
            async for _ in kernel.process_turn_stream("Demand a true weigh"):
                pass

        assert kernel.state.session.turn_count == turn_before
        assert kernel.state.soul_ledger.vectors.bia == bia_before
        assert kernel.state.pending_vignette is not None

    @pytest.mark.asyncio
    async def test_invalid_escalation_preserves_the_armed_vignette(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        # "fly" makes mock Lachesis reject — an invalid free-text while buttons pend.
        result = await kernel.process_turn("I fly away into the clouds")
        # The armed vignette survives; the player's buttons are not destroyed.
        assert kernel.state.pending_vignette is not None
        assert kernel.state.pending_vignette.vignette_id == "test_beat"
        assert result.terminal is False

    @pytest.mark.asyncio
    async def test_vignette_never_kills(self, kernel):
        """P1-C4: no lethal machinery on the cheap beat — even a collapsed soul
        survives the vignette; the Fates collect at the chapter's crucible."""
        await _adult_kernel(kernel)
        _arm(kernel)
        v = kernel.state.soul_ledger.vectors
        v.metis = v.bia = v.kleos = v.aidos = 0.5  # dead-soul territory
        result = await kernel.process_turn("Keep your head down")
        assert result.terminal is False
        assert kernel.state.terminal is False


class TestChapterFlow:
    @pytest.mark.asyncio
    async def test_crucible_closes_chapter_and_ages(self, kernel):
        await _adult_kernel(kernel)
        # The Fork's finalize recorded a crucible: chapter closed at least once.
        assert kernel.state.session.chapter_index >= 1
        age_before = kernel.state.session.player_age
        chapters_before = kernel.state.session.chapter_index
        kernel.state.pending_vignette = None  # force the full pipeline
        await kernel.process_turn("I press on through the day")
        assert kernel.state.session.chapter_index == chapters_before + 1
        assert kernel.state.session.player_age == age_before + 1  # a year per chapter

    @pytest.mark.asyncio
    async def test_adult_age_does_not_advance_per_turn(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        age_before = kernel.state.session.player_age
        await kernel.process_turn("Keep your head down")  # a vignette beat
        assert kernel.state.session.player_age == age_before  # no per-beat aging

    @pytest.mark.asyncio
    async def test_scheduled_vignette_survives_serialization(self, kernel):
        """Durability: an armed pending vignette round-trips, so a resumed
        thread re-presents exactly the buttons it left."""
        from app.schemas.state import ThreadState
        await _adult_kernel(kernel)
        _arm(kernel)
        restored = ThreadState.model_validate_json(kernel.state.model_dump_json())
        assert restored.pending_vignette is not None
        assert [c.label for c in restored.pending_vignette.choices] == [
            "Demand a true weigh", "Mark your carts secretly", "Keep your head down",
        ]


class TestTheSeal:
    """The bow ruling: the engine appends the authored consequence as the
    scene's final line — the model writes the middle, the math writes the
    ending. The box audibly shuts."""

    @pytest.mark.asyncio
    async def test_sync_scene_ends_on_the_authored_seal(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel, evolution="The scale is watched now.")
        result = await kernel.process_turn("Demand a true weigh")
        assert "⁂ The scale is watched now." in result.prose
        # The committed scene's last line IS the seal.
        assert kernel.state.prose_history[-1].rstrip().endswith(
            "⁂ The scale is watched now."
        )

    @pytest.mark.asyncio
    async def test_stream_emits_the_seal_as_its_own_frame(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel, evolution="The scale is watched now.")
        frames = [f async for f in kernel.process_turn_stream("Demand a true weigh")]
        payloads = [json.loads(f[len("data: "):]) for f in frames if f.startswith("data: ")]
        prose_texts = [p["text"] for p in payloads if p.get("type") == "prose"]
        seal_frames = [t for t in prose_texts if t.strip().startswith("⁂ ")]
        assert len(seal_frames) == 1
        assert seal_frames[0].strip() == "⁂ The scale is watched now."

    @pytest.mark.asyncio
    async def test_exactly_one_seal_per_scene(self, kernel):
        """The mock middle carries no consequence text — only the engine
        appends it; exactly ONE seal exists in the committed scene."""
        await _adult_kernel(kernel)
        _arm(kernel, evolution="The scale is watched now.")
        await kernel.process_turn("Demand a true weigh")
        committed = kernel.state.prose_history[-1]
        assert committed.count("The scale is watched now.") == 1
        assert committed.count("⁂") == 1


class TestVignetteStream:
    @pytest.mark.asyncio
    async def test_stream_emits_three_frames_and_no_council(self, kernel):
        await _adult_kernel(kernel)
        _arm(kernel)
        _boobytrap_council(kernel)
        frames = [f async for f in kernel.process_turn_stream("Demand a true weigh")]
        payloads = [json.loads(f[len("data: "):]) for f in frames if f.startswith("data: ")]
        kinds = [p.get("type") for p in payloads]
        # Calibration: vignette prose now STREAMS — mechanic, then 1+ prose
        # token frames, then exactly one closing state frame.
        assert kinds[0] == "mechanic"
        assert kinds[-1] == "state"
        assert len(kinds) >= 3 and all(k == "prose" for k in kinds[1:-1])
        mech = payloads[0]["payload"]
        assert mech["outcome"] == "vignette" and mech["valid"] is True
        assert payloads[-1]["terminal"] is False
