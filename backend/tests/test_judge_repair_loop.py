"""Sophia <-> kernel: the critique-brief repair loop + zero state authority.

The mock Sophia passes on grounded play, so the loop itself is exercised by
monkeypatching kernel.sophia.judge with controlled critique sequences. Eris is
gated off so game-math is deterministic, which lets the zero-authority test
compare a pass-run against a revise-run byte-for-byte.
"""

from __future__ import annotations

import pytest

from app.core.kernel import NyxKernel
from app.schemas.judge import JudgeCritique, JudgeViolation


@pytest.fixture(autouse=True)
def _no_eris(monkeypatch):
    import app.agents.eris as eris_module
    monkeypatch.setattr(eris_module.random, "random", lambda: 0.999)


async def _init(kernel: NyxKernel, player_id: str = "judge_test") -> None:
    await kernel.initialize(
        hamartia="Wrath of the Untempered", player_id=player_id,
        name="Orin", gender="boy",
        first_memory="The weight of a heavy stone in my hand.",
    )


def _revise(brief: str = "Rewrite the scene: 1) remove comfort. Output fresh prose, not an explanation.") -> JudgeCritique:
    return JudgeCritique(
        verdict="revise",
        violations=[JudgeViolation(axis="tragedy", severity="hard", detail="too kind")],
        critique_brief=brief,
    )


async def _always_pass(prose, ctx):
    return JudgeCritique(verdict="pass")


def _count_clotho(kernel, monkeypatch, counter):
    real = kernel._request_clotho_pass

    async def counting(ctx, action, *, repair_brief=""):
        counter["n"] += 1
        return await real(ctx, action, repair_brief=repair_brief)

    monkeypatch.setattr(kernel, "_request_clotho_pass", counting)


def _game_math(state) -> tuple:
    return (
        state.soul_ledger.vectors.model_dump(),
        state.pressures.model_dump(),
        state.doom.model_dump(),
        tuple(o.model_dump_json() for o in state.soul_ledger.active_oaths),
    )


class TestRepairLoop:
    @pytest.mark.asyncio
    async def test_revise_then_pass_commits_one_regeneration(self, monkeypatch):
        kernel = NyxKernel()
        await _init(kernel)
        counter = {"n": 0}
        _count_clotho(kernel, monkeypatch, counter)
        seq = [_revise(), JudgeCritique(verdict="pass")]

        async def fake_judge(prose, ctx):
            return seq.pop(0) if seq else JudgeCritique(verdict="pass")

        monkeypatch.setattr(kernel.sophia, "judge", fake_judge)
        result = await kernel.process_turn("attack the guard")
        assert not result.terminal
        assert counter["n"] == 2                 # base draft + exactly one regenerate

    @pytest.mark.asyncio
    async def test_happy_path_adds_no_extra_clotho_call(self, monkeypatch):
        kernel = NyxKernel()
        await _init(kernel)
        counter = {"n": 0}
        _count_clotho(kernel, monkeypatch, counter)
        # default mock Sophia passes on the grounded substrate
        await kernel.process_turn("attack the guard")
        assert counter["n"] == 1

    @pytest.mark.asyncio
    async def test_non_convergence_keeps_original_and_defers_brief(self, monkeypatch):
        kernel = NyxKernel()
        await _init(kernel)

        async def always_revise(prose, ctx):
            return _revise()

        monkeypatch.setattr(kernel.sophia, "judge", always_revise)
        result = await kernel.process_turn("attack the guard")
        assert not result.terminal
        assert any("Rewrite" in note for note in result.state.craft_notes)  # brief deferred
        assert len(result.state.craft_notes) <= 3                            # craft_notes_max

    @pytest.mark.asyncio
    async def test_craft_notes_never_exceed_cap(self, monkeypatch):
        kernel = NyxKernel()
        await _init(kernel)

        async def always_revise(prose, ctx):
            return _revise()

        monkeypatch.setattr(kernel.sophia, "judge", always_revise)
        for action in ("hide", "rest", "observe", "wait", "watch"):
            result = await kernel.process_turn(action)
            if result.terminal:
                break
            assert len(result.state.craft_notes) <= 3


class TestZeroStateAuthority:
    @pytest.mark.asyncio
    async def test_judge_loop_writes_no_state(self, monkeypatch):
        # A: Sophia passes. B: Sophia revises then passes (forces a regenerate).
        # With Eris off, game-math is deterministic, so any difference would be
        # the judge writing state — there must be none (ADJ-E2).
        ka = NyxKernel()
        await _init(ka)
        monkeypatch.setattr(ka.sophia, "judge", _always_pass)
        ra = await ka.process_turn("attack the guard")

        kb = NyxKernel()
        await _init(kb)
        seq = [_revise(), JudgeCritique(verdict="pass")]

        async def fake_judge(prose, ctx):
            return seq.pop(0) if seq else JudgeCritique(verdict="pass")

        monkeypatch.setattr(kb.sophia, "judge", fake_judge)
        rb = await kb.process_turn("attack the guard")

        assert _game_math(ra.state) == _game_math(rb.state)


class TestDeathUnjudged:
    @pytest.mark.asyncio
    async def test_death_prose_is_never_judged(self, monkeypatch):
        kernel = NyxKernel()
        await _init(kernel)
        calls = {"n": 0}

        async def spy(prose, ctx):
            calls["n"] += 1
            return JudgeCritique()

        monkeypatch.setattr(kernel.sophia, "judge", spy)
        result = await kernel.process_turn("embrace the void")
        assert result.terminal               # self-destruct, Eris off → no miracle
        assert calls["n"] == 0               # death prose bypasses Sophia entirely (ADJ-E6)


class TestRegenIsCommitted:
    """The committed prose must be Sophia's APPROVED regeneration, not the base
    draft she rejected. Regression for the sync-path parity defect: a stale base
    validation (repair_needed=True) used to overwrite the clean regen inside
    _finalize_turn, silently reverting the whole adjudication tier.
    """

    @pytest.mark.asyncio
    async def test_regen_prose_is_committed_not_the_rejected_base_draft(self, monkeypatch):
        from app.schemas.state import MomusValidation

        kernel = NyxKernel()
        await _init(kernel)

        ORIG = "The hearth was warm and Orin felt, for once, wholly safe and unafraid here."
        ORIG_CORRECTED = "The hearth was warm and Orin felt, for once, a little less exposed."
        REGEN = "The hearth guttered; Orin counted the exits and trusted none of the dark."

        async def fake_clotho(ctx, action, *, repair_brief=""):
            # The repair_brief is only set on the regeneration pass.
            return (REGEN, ["wait", "leave"]) if repair_brief else (ORIG, ["stay", "go"])

        monkeypatch.setattr(kernel, "_request_clotho_pass", fake_clotho)

        async def fake_momus(prose, state):
            if prose == ORIG:
                # exactly one hallucination -> minor drift -> commit corrected,
                # repair_needed=True (the stale validation that used to win).
                return MomusValidation(
                    valid=False,
                    hallucinations=["a comfort canon denies"],
                    repair_needed=True,
                    corrected_prose=ORIG_CORRECTED,
                )
            return MomusValidation(valid=True)   # the regen is factually clean

        monkeypatch.setattr(kernel.momus, "validate_prose", fake_momus)

        async def fake_judge(prose, ctx):
            # Sophia rejects the base corrected draft, approves the regen.
            if prose == REGEN:
                return JudgeCritique(verdict="pass")
            return _revise()

        monkeypatch.setattr(kernel.sophia, "judge", fake_judge)

        result = await kernel.process_turn("tend the fire")
        assert not result.terminal
        assert result.prose == REGEN, result.prose            # not the rejected draft
        assert kernel.state.prose_history[-1] == REGEN        # memory records the regen
        assert ORIG_CORRECTED not in kernel.state.prose_history
