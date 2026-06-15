"""Authored scripts that drive deterministic lives through the kernel.

A LifeScript is a fixed, seeded sequence of player actions plus the
ground-truth labels the engine cannot supply itself (which turns are
genuinely exploitative; which world the life must draw). Pure data —
no kernel import (CAL-E4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifeScript:
    """One scripted life: identity, a fixed action list, and ground truth."""

    label: str                      # human label for reports/tests
    first_memory: str               # carries the archetype keyword
    hamartia: str
    actions: tuple[str, ...]
    expected_world_id: str          # the frozen-set world this life MUST draw
    seed: int = 1
    player_id: str = "sim_player"
    name: str = "Sim"
    gender: str = "boy"
    turn_cap: int = 40
    eris_off: bool = True           # patch the Eris gate off for a clean stream
    run_number: int = 1
    # HAND-AUTHORED per-turn ground truth: is action[i] a genuine exploit
    # (a repeated/abusive pattern), judged from in-fiction intent — NEVER
    # from the engine's string-equality predicate (CAL-E4). Length must
    # equal len(actions) when supplied.
    is_exploit_turn: tuple[bool, ...] = ()
    # Scenario assertion (optional): the closed-enum death bucket this
    # life is authored to reach.
    expected_death_bucket: str | None = None
    # Part of the LOCKED compliance-floor corpus: committed-but-legitimate
    # play that MUST stay unpunished (CAL-E7).
    legitimate: bool = False

    def __post_init__(self) -> None:
        if self.is_exploit_turn and len(self.is_exploit_turn) != len(self.actions):
            raise ValueError(
                f"{self.label}: is_exploit_turn length "
                f"{len(self.is_exploit_turn)} != actions length {len(self.actions)}"
            )


@dataclass(frozen=True)
class ParaphrasePair:
    """A plain action that hits the keyword vocabulary and a smuggled
    paraphrase with identical in-fiction intent that misses the tokens."""

    label: str
    plain: str
    smuggled: str
    leak_category: str          # "violent" | "deceptive" | "public" | ...
    ground_truth_pressure: str  # the consequence the plain form earns
