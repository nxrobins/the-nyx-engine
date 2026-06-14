"""Friction metrics over LifeOutcomes — pure aggregation, no engine logic.

Imports NOTHING from app.services.pressure (CAL-E4): death buckets are
reconstructed from the trace + final vectors + atropos keywords (never the
free-text death_reason, CAL-E6), and exploit precision/recall is scored
against hand-authored labels — so the metric can register leaks the
engine's own string-equality predicate misses, and cannot agree with it
tautologically.

The optimization target these metrics serve is FRICTION, never retention
or player satisfaction (CAL-E7). See README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from sim.outcome import DEATH_BUCKETS, LifeOutcome

_VECTOR_KEYS = ("metis", "bia", "kleos", "aidos")
_ESCAPABLE_BUCKETS = frozenset({"wounds", "faction_heat"})
_INESCAPABLE_BUCKETS = frozenset({"broken_oath", "clock"})
_PUNISH_TYPES = frozenset({"punishment", "lethal_punishment"})


# ---------------------------------------------------------------------------
# Death classification — closed enum, reconstructed from the trace (CAL-E6)
# ---------------------------------------------------------------------------

def classify_death(outcome: LifeOutcome) -> str:
    """Map a life to exactly one closed-enum bucket.

    Mirrors Atropos's own precedence (doom terminal > dead soul > keyword),
    reading the recorded doom snapshots + terminal vectors + the configured
    death keywords — never the prose death_reason or state.doom.active.
    """
    if outcome.capped:
        return "__capped__"
    if not outcome.turns:
        return "narrative_dead_end"
    last = outcome.turns[-1]
    # 1) A doom matured this turn.
    if last.doom.active and last.doom.stage >= last.doom.max_stage:
        return last.doom.cause if last.doom.cause in DEATH_BUCKETS else "clock"
    # 2) Dead soul — every vector collapsed to <= 1.0.
    if all(outcome.final_vectors.get(k, 10.0) <= 1.0 for k in _VECTOR_KEYS):
        return "dead_soul"
    # 3) Self-destruction keyword in the terminal action.
    lowered = last.action.lower()
    if any(kw in lowered for kw in settings.atropos_death_keywords):
        return "self_destruct_keyword"
    # 4) Anything else the engine severed (in mock, the LLM dead-end is off).
    return "narrative_dead_end"


# ---------------------------------------------------------------------------
# Exploit precision / recall — against HAND-AUTHORED labels (CAL-E4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExploitScore:
    labeled: int          # ground-truth exploit turns scored
    engine_positive: int  # turns the engine escalated to punishment/lethal
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float:
        d = self.true_positive + self.false_positive
        return round(self.true_positive / d, 4) if d else 1.0

    @property
    def recall(self) -> float:
        d = self.true_positive + self.false_negative
        return round(self.true_positive / d, 4) if d else 1.0


def exploit_score(outcomes: list[LifeOutcome]) -> ExploitScore:
    tp = fp = fn = labeled = engine_pos = 0
    for o in outcomes:
        if not o.is_exploit_turn:
            continue
        for label, turn in zip(o.is_exploit_turn, o.turns):
            positive = turn.nemesis_type in _PUNISH_TYPES
            labeled += int(bool(label))
            engine_pos += int(positive)
            if label and positive:
                tp += 1
            elif positive and not label:
                fp += 1
            elif label and not positive:
                fn += 1
    return ExploitScore(labeled, engine_pos, tp, fp, fn)


# ---------------------------------------------------------------------------
# Doom economy — escapable vs inescapable (CAL-E6 consistency source)
# ---------------------------------------------------------------------------

def _had_doom(o: LifeOutcome, escapable: bool) -> bool:
    return any(t.doom.active and t.doom.escapable == escapable for t in o.turns)


def doom_economy(outcomes: list[LifeOutcome]) -> dict:
    buckets = [classify_death(o) for o in outcomes]
    escapable_lives = sum(1 for o in outcomes if _had_doom(o, True))
    escapable_deaths = sum(1 for b in buckets if b in _ESCAPABLE_BUCKETS)
    inescapable_lives = sum(1 for o in outcomes if _had_doom(o, False))
    inescapable_deaths = sum(1 for b in buckets if b in _INESCAPABLE_BUCKETS)
    return {
        "escapable_lives": escapable_lives,
        "escapable_deaths": escapable_deaths,
        "escapable_escapes": max(escapable_lives - escapable_deaths, 0),
        "escapable_escape_rate": (
            round(max(escapable_lives - escapable_deaths, 0) / escapable_lives, 4)
            if escapable_lives else 0.0
        ),
        "inescapable_lives": inescapable_lives,
        "inescapable_deaths": inescapable_deaths,
        # Alive past an inescapable doom = a smuggle-through. MUST be 0 with
        # Eris off; a non-zero value is a calibration alarm.
        "inescapable_smuggle": max(inescapable_lives - inescapable_deaths, 0),
    }


# ---------------------------------------------------------------------------
# The full report
# ---------------------------------------------------------------------------

@dataclass
class FrictionReport:
    n_lives: int
    death_cause_mix: dict
    doom: dict
    exploit: ExploitScore
    avg_died_turn: float
    epochs_reached: dict
    oath_economy: dict
    promise_economy: dict
    imbalance_at_death: dict

    def to_dict(self) -> dict:
        return {
            "n_lives": self.n_lives,
            "death_cause_mix": dict(sorted(self.death_cause_mix.items())),
            "doom": dict(sorted(self.doom.items())),
            "exploit": {
                "labeled": self.exploit.labeled,
                "engine_positive": self.exploit.engine_positive,
                "true_positive": self.exploit.true_positive,
                "false_positive": self.exploit.false_positive,
                "false_negative": self.exploit.false_negative,
                "precision": self.exploit.precision,
                "recall": self.exploit.recall,
            },
            "avg_died_turn": self.avg_died_turn,
            "epochs_reached": dict(sorted(self.epochs_reached.items())),
            "oath_economy": dict(sorted(self.oath_economy.items())),
            "promise_economy": dict(sorted(self.promise_economy.items())),
            "imbalance_at_death": dict(sorted(self.imbalance_at_death.items())),
        }


def _histogram(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def build_report(outcomes: list[LifeOutcome]) -> FrictionReport:
    n = len(outcomes)
    mix: dict[str, int] = {b: 0 for b in DEATH_BUCKETS}
    for o in outcomes:
        bucket = classify_death(o)
        if bucket not in mix:                       # CAL-E6: no fall-through
            raise ValueError(f"{o.label}: death bucket '{bucket}' outside the closed enum")
        mix[bucket] += 1
    mix = {k: v for k, v in mix.items() if v}        # drop empty buckets from the artifact

    verdicts = [o.verdict for o in outcomes if o.verdict is not None]
    oaths_sworn = sum(v.oaths_sworn for v in verdicts)
    oaths_broken = sum(v.oaths_broken for v in verdicts)
    oaths_fulfilled = sum(v.oaths_fulfilled for v in verdicts)
    planted = sum(v.promises_planted for v in verdicts)
    paid = sum(v.promises_paid for v in verdicts)
    abandoned = sum(v.promises_abandoned for v in verdicts)
    imbalances = [round(v.imbalance, 1) for v in verdicts]

    return FrictionReport(
        n_lives=n,
        death_cause_mix=mix,
        doom=doom_economy(outcomes),
        exploit=exploit_score(outcomes),
        avg_died_turn=round(sum(o.died_turn for o in outcomes) / n, 2) if n else 0.0,
        epochs_reached=_histogram(o.died_turn // 3 for o in outcomes),
        oath_economy={"sworn": oaths_sworn, "broken": oaths_broken, "fulfilled": oaths_fulfilled},
        promise_economy={"planted": planted, "paid": paid, "abandoned": abandoned},
        imbalance_at_death=_histogram(imbalances),
    )
