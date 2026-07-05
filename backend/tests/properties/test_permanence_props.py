"""Commitment 1 (consequence is law) — death permanence under generation.

The terminal latch (audit C1) must hold against *any* action a player could
send after death, not just the benign examples in test_terminal_latch.py. This
drives generated action text — arbitrary unicode, injection-shaped strings,
empty — at a severed kernel from generated post-death turn/soul states, and
asserts the thread stays dead and unchanged every time.

This is the seed of the fuller stateful "life fuzzer" (a RuleBasedStateMachine
driving whole random lives); that lands as its own slice. Here we pin the
narrow, load-bearing invariant: dead stays dead, for all inputs.
"""

from __future__ import annotations

import asyncio

from hypothesis import given
from hypothesis import strategies as st

from app.core.kernel import NyxKernel
from app.schemas.state import SoulVectors, ThreadState

# One kernel, reused across examples: constructing NyxKernel spins up a ChromaDB
# client, so we build it once and reset a fresh terminal state per example. The
# guard is read-only and returns before touching anything, so reuse is safe.
_KERNEL: NyxKernel | None = None


def _severed_kernel() -> NyxKernel:
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = NyxKernel()
    return _KERNEL


_souls = st.builds(
    SoulVectors,
    metis=st.floats(0, 10), bia=st.floats(0, 10),
    kleos=st.floats(0, 10), aidos=st.floats(0, 10),
)


@given(
    action=st.text(max_size=300),
    turn=st.integers(min_value=0, max_value=300),
    vectors=_souls,
    reason=st.text(max_size=120),
)
def test_severed_thread_refuses_every_action(action, turn, vectors, reason):
    k = _severed_kernel()
    k.state = ThreadState()
    k.state.terminal = True
    k.state.death_reason = reason
    k.state.session.turn_count = turn
    k.state.soul_ledger.vectors = vectors
    before = vectors.model_dump()

    result = asyncio.run(k.process_turn(action))

    assert result.terminal is True
    assert k.state.terminal is True                          # stays dead
    assert k.state.session.turn_count == turn                # no advance
    assert k.state.soul_ledger.vectors.model_dump() == before  # no mutation
