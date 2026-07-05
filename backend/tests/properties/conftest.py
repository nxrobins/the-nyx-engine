"""Property-based test foundation (Hypothesis).

The five commitments of the true north are invariants; properties are their
executable form. This package holds them — one module per commitment area — and
this conftest registers the Hypothesis profiles that govern how hard they run.

Profiles (select with the HYPOTHESIS_PROFILE env var; CI is auto-detected):
  - dev   : fast, randomized — the default for local `pytest` runs.
  - ci    : more examples, derandomized (reproducible) — auto-selected when the
            CI env var is set, so the CI workflow needs no special flag.
  - deep  : a large randomized sweep — the loop's productive idle work while
            holding on a merge or a creative decision (HYPOTHESIS_PROFILE=deep).

`deadline=None` throughout: these properties may exercise slow deterministic
paths (kernel turns, canon mutation), and a wall-clock deadline would make them
flaky rather than meaningful. Correctness, not latency, is what they pin.

The top-level tests/conftest.py autouse fixture still applies here, so every
property that touches an agent or the kernel is hermetic (mock mode, no keys,
tmp dirs) by construction.
"""

from __future__ import annotations

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=50, deadline=None)
settings.register_profile("ci", max_examples=300, derandomize=True, deadline=None)
settings.register_profile("deep", max_examples=3000, deadline=None)

_profile = os.getenv("HYPOTHESIS_PROFILE") or ("ci" if os.getenv("CI") else "dev")
settings.load_profile(_profile)
