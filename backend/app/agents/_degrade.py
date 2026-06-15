"""The Throttle — visible degradation (the single coverage point).

Every agent guards `model == "mock"` at the top and returns deterministic mock
output; its real-model branch then catches LLM exceptions and silently swaps in
that SAME mock output. Under concurrent real-model load a provider 429/timeout is
therefore indistinguishable from intended mock mode — a silent quality collapse.

This module makes that fallback OBSERVABLE without changing it: every one of the
agents' `except` sites calls `note_degraded(label, model, error)` before returning
its mock fallback. The game still always continues (the safety net is untouched);
the collapse is just no longer silent.

THR-C1 — coverage is STRUCTURAL: ONE helper, called from ALL fallback sites, so a
new agent or a missed site is a one-line omission, not a per-agent reimplementation.
THR-C2 — the discriminator is `model != "mock"`: under the hermetic mock pin the
agent returns at its top guard and never reaches here, so this is provably inert in
the test suite (zero false positives). THR-C7 — `_DEGRADED` is module-level; the
conftest autouse fixture resets it per-test so absolute-count assertions stay
order-independent.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("nyx.degrade")

_LOCK = threading.Lock()
_DEGRADED: dict[str, int] = {}   # label -> count of real-model -> mock fallbacks


def note_degraded(label: str, model: str, error: BaseException) -> None:
    """Record a real-model -> mock fallback. No-op in mock mode (THR-C2).

    `label` is an explicit per-site string (e.g. "clotho", "clotho.stream",
    "atropos.deadend") so sub-paths are distinguishable in telemetry. `model` is
    the captured model local from the except — if it is "mock" this is a no-op.
    """
    if model == "mock":
        return
    with _LOCK:
        _DEGRADED[label] = _DEGRADED.get(label, 0) + 1
    logger.warning(
        "AGENT DEGRADED: %s fell back to mock after %r (model=%s)", label, error, model
    )


def degraded_counts() -> dict[str, int]:
    """A snapshot of the per-label degradation counts (telemetry / tests)."""
    with _LOCK:
        return dict(_DEGRADED)


def reset_degraded() -> None:
    """Test hook (THR-C7): clear the module-level counter between tests."""
    with _LOCK:
        _DEGRADED.clear()
