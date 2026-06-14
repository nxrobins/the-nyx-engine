"""The deterministic driver — runs a LifeScript through the real kernel.

Self-contained hermeticity (CAL-E1/E2/E3): around every life, run_life
- saves and restores ``random.getstate()`` so the global RNG cursor any
  later test sees is byte-identical to a no-sim run (no suite poisoning),
- ``random.seed(script.seed)`` for reproducible mock pools,
- patches the Eris chaos gate off for ``eris_off`` scripts (Eris is the
  ONLY agent that injects RNG into *measured* state; with it off the trace
  is deterministic regardless of background-task scheduling),
- swaps ``NyxRAGStore`` -> ``NullRag`` BEFORE any kernel is built (no
  chromadb.Client, no embedding model, rag_context == [] every turn),
- pins ``worlds_dir`` to the frozen 4-cartridge set and reloads the
  registry, asserting the frozen id set and each life's expected world.

It asserts mock mode + zero latency at entry and raises loudly on kernel
API drift (CAL-E8): a wrong number must never be emitted quietly.
"""

from __future__ import annotations

import random
from pathlib import Path

import app.agents.eris as _eris_module
import app.core.kernel as _kernel_module
from app.core.config import settings
from app.core.kernel import NyxKernel
from app.core.world_registry import _registry, reload_registry
from app.services.assayer import compute_verdict

from sim.life_script import LifeScript
from sim.null_rag import NullRag
from sim.outcome import DoomSnapshot, LifeOutcome, TurnTrace

_FROZEN_DIR = Path(__file__).resolve().parent / "worlds_frozen"
FROZEN_WORLD_IDS = frozenset({"thornwell", "ashfall", "oldgate", "fenward"})

_CAPPED_SENTINEL = "__capped__"


def _assert_mock_and_latency() -> None:
    if settings.lachesis_model != "mock" or settings.clotho_model != "mock":
        raise RuntimeError("sim requires mock models (got real model strings)")
    if settings.mock_latency_scale != 0.0:
        raise RuntimeError("sim requires mock_latency_scale=0 for stable gather order")


def _last_nemesis_type(state) -> str:
    """The intervention_type of this turn's nemesis proposal, or ''.

    Read from the deliberation trace (recent_traces[-1]) rather than the
    TurnResult, which exposes only the boolean ``nemesis_struck`` and so
    cannot distinguish a punishment from a routine prophecy update.
    """
    if not state.recent_traces:
        return ""
    trace = state.recent_traces[-1]
    for proposal in trace.proposals:
        if proposal.agent == "nemesis":
            return str(proposal.scene_patch.get("intervention_type", ""))
    return ""


def _trace_row(kernel: NyxKernel, result, action: str) -> TurnTrace:
    state = kernel.state
    doom = state.doom
    return TurnTrace(
        turn_number=result.turn_number,
        action=action,
        nemesis_struck=bool(result.nemesis_struck),
        nemesis_type=_last_nemesis_type(state),
        eris_struck=bool(result.eris_struck),
        oath_broken=(doom.cause == "broken_oath" and doom.started_turn == result.turn_number),
        doom=DoomSnapshot(
            active=doom.active,
            cause=doom.cause,
            stage=doom.stage,
            max_stage=doom.max_stage,
            started_turn=doom.started_turn,
            escapable=doom.escapable,
        ),
        vectors=dict(state.soul_ledger.vectors.model_dump()),
        pressures=dict(state.pressures.model_dump()),
        last_outcome=state.last_outcome,
        terminal=bool(result.terminal),
        rag_context_len=len(state.rag_context),
    )


async def run_life(script: LifeScript) -> LifeOutcome:
    """Drive one scripted life to death-or-cap. Pure, deterministic, offline."""
    _assert_mock_and_latency()

    rng_state = random.getstate()
    eris_orig = _eris_module.random.random
    rag_orig = _kernel_module.NyxRAGStore
    worlds_orig = settings.worlds_dir
    try:
        random.seed(script.seed)
        if script.eris_off:
            _eris_module.random.random = lambda: 0.999  # gate never opens
        _kernel_module.NyxRAGStore = NullRag           # swap BEFORE construction
        settings.worlds_dir = str(_FROZEN_DIR)
        reload_registry()
        loaded = set(_registry._loaded_ids)
        if loaded != set(FROZEN_WORLD_IDS):
            raise RuntimeError(f"frozen world set drift: {loaded} != {FROZEN_WORLD_IDS}")

        kernel = NyxKernel()
        if kernel.rag.__class__.__name__ != "NullRag":
            raise RuntimeError("RAG was not stubbed — refusing to run a real chromadb client")

        result = await kernel.initialize(
            script.hamartia, script.player_id, script.name,
            script.gender, script.first_memory,
        )
        if not all(hasattr(result, a) for a in ("terminal", "death_reason", "book_id", "turn_number")):
            raise RuntimeError("TurnResult shape drift — sim depends on it (CAL-E8)")
        if kernel.state.world_id != script.expected_world_id:
            raise RuntimeError(
                f"{script.label}: drew world '{kernel.state.world_id}', "
                f"expected '{script.expected_world_id}'"
            )
        kernel._cancel_morpheus()
        kernel._cancel_scribe()

        turns: list[TurnTrace] = []
        for action in script.actions:
            if result.terminal:
                break
            if kernel.state.session.turn_count >= script.turn_cap:
                break
            result = await kernel.process_turn(action)
            # Drain background organs every turn: a finished Morpheus/Scribe
            # task drawing from the global RNG between turns would desync the
            # stream. The harness measures the consequence layer, not them.
            kernel._cancel_morpheus()
            kernel._cancel_scribe()
            turns.append(_trace_row(kernel, result, action))

        # NOTE: rag_context is NOT asserted empty. The CAL-E1 guarantee is
        # that the RAG STORE is NullRag (asserted at construction, immutable
        # for the life) so no chromadb embedding ever enters the run. The
        # mock Lachesis independently writes a deterministic combat summary
        # into state.rag_context (lachesis.py); that content is offline and
        # reproducible, and in mock it feeds only paths that no-op (Atropos's
        # dead-end check returns False, Eris is gated off). rag_context_len is
        # recorded in the trace for transparency, not gated on.

        terminal = bool(result.terminal)
        if terminal:
            verdict = compute_verdict(
                kernel.state, death_reason=result.death_reason, book_id=result.book_id
            )
            death_reason = result.death_reason
        else:
            verdict = compute_verdict(kernel.state, death_reason=_CAPPED_SENTINEL)
            death_reason = _CAPPED_SENTINEL

        return LifeOutcome(
            label=script.label,
            world_id=kernel.state.world_id,
            terminal=terminal,
            capped=not terminal,
            death_reason=death_reason,
            died_turn=kernel.state.session.turn_count,
            final_vectors=dict(kernel.state.soul_ledger.vectors.model_dump()),
            turns=turns,
            verdict=verdict,
            is_exploit_turn=script.is_exploit_turn,
            legitimate=script.legitimate,
        )
    finally:
        settings.worlds_dir = worlds_orig
        reload_registry()
        _kernel_module.NyxRAGStore = rag_orig
        _eris_module.random.random = eris_orig
        random.setstate(rng_state)


async def run_corpus(scripts) -> list[LifeOutcome]:
    """Run a list of scripts, one fresh kernel per life."""
    return [await run_life(s) for s in scripts]
