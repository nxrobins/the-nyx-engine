"""The red-team smuggle-through harness — friction across the input boundary.

Two grounded attack classes:
  * DOOM-ESCAPE: scripted in the corpus (inescapable dooms MUST mature); the
    measurement (``inescapable_smuggle == 0``) lives in metrics.doom_economy.
  * KEYWORD-EVASION (the headline): ``diff_paraphrase`` isolates the pure
    keyword-classifier contribution and counts how often a paraphrase with
    identical in-fiction intent earns a strictly weaker consequence than its
    plain twin. Punishment-reframe (class 2) is NOT measured independently —
    against deterministic token detectors it is a tautology (a paraphrased
    betrayal scores zero on BOTH the engine and a token oracle); it folds into
    this keyword-leak finding (AG-CAL-2).

``diff_paraphrase`` CALLS the real ``evolve_pressures`` — the authoritative
detector. The point is to MEASURE it, not re-implement it; this module copies
none of the keyword sets, the normalizer, or the repeat rule (CAL-E4 in
spirit; the no-pressure-import assert is scoped to metrics.py, where tautology
is the risk). Isolation (CAL-E5):
  * ``last_action`` is held IDENTICAL between twins (a neutral string neither
    matches) so the +1.0 exact-repeat term cancels;
  * a quiet ResolvedOutcome zeroes the nemesis/eris/oath/terminal folds;
  * ``proposal_pressure={"omen": 2.0}`` forces ``stable_turn=False`` for BOTH
    twins, so the -0.1 suspicion/faction "quiet decay" never fires
    asymmetrically (and the omen stabilizer, excluded from the diff, cancels);
  * ``hamartia_profile`` is None (no social_cost_bias fold).
The diff is taken over the six keyword-attributable axes only.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.resolver import ResolvedOutcome
from app.schemas.state import ThreadState
from app.services.pressure import evolve_pressures  # CALL the detector, never copy it

from sim.life_script import ParaphrasePair

_NEUTRAL_LAST_ACTION = "they consider the matter in silence"
_KEYWORD_AXES = ("suspicion", "scarcity", "wounds", "debt", "faction_heat", "exploit_score")
_STABILIZER = {"omen": 2.0}  # forces stable_turn False; omen is excluded from the diff


def _keyword_delta(action: str) -> dict[str, float]:
    """The pure keyword-branch pressure contribution of one action."""
    state = ThreadState(last_action=_NEUTRAL_LAST_ACTION)
    quiet = ResolvedOutcome(state=state)  # all fold flags default to False/empty
    # Assert the neutralization actually held before trusting the diff (CAL-E5).
    assert not quiet.nemesis_struck and not quiet.eris_struck
    assert not quiet.oath_broken and not quiet.terminal
    assert state.last_action == _NEUTRAL_LAST_ACTION
    assert state.soul_ledger.hamartia_profile is None
    ev = evolve_pressures(state, action, quiet, proposal_pressure=dict(_STABILIZER))
    return {k: round(ev.delta.get(k, 0.0), 4) for k in _KEYWORD_AXES}


@dataclass(frozen=True)
class PressureDiff:
    label: str
    leak_category: str
    plain_delta: dict
    smuggled_delta: dict
    per_axis_diff: dict      # plain - smuggled, per keyword axis (repeat term cancels)
    plain_harm: float
    smuggled_harm: float
    smuggled_through: bool   # smuggled earns a strictly weaker consequence


def diff_paraphrase(pair: ParaphrasePair) -> PressureDiff:
    plain = _keyword_delta(pair.plain)
    smug = _keyword_delta(pair.smuggled)
    per_axis = {k: round(plain[k] - smug[k], 4) for k in _KEYWORD_AXES}
    plain_harm = round(sum(plain.values()), 4)
    smug_harm = round(sum(smug.values()), 4)
    return PressureDiff(
        label=pair.label,
        leak_category=pair.leak_category,
        plain_delta=plain,
        smuggled_delta=smug,
        per_axis_diff=per_axis,
        plain_harm=plain_harm,
        smuggled_harm=smug_harm,
        smuggled_through=smug_harm < plain_harm,
    )


@dataclass
class SmuggleReport:
    pairs: int
    smuggled_through: int
    by_category: dict
    diffs: list

    @property
    def smuggle_rate(self) -> float:
        return round(self.smuggled_through / self.pairs, 4) if self.pairs else 0.0

    def to_dict(self) -> dict:
        return {
            "pairs": self.pairs,
            "smuggled_through": self.smuggled_through,
            "smuggle_rate": self.smuggle_rate,
            "by_category": {
                k: dict(sorted(v.items())) for k, v in sorted(self.by_category.items())
            },
            "detail": sorted(
                (
                    {
                        "label": d.label,
                        "category": d.leak_category,
                        "plain_harm": d.plain_harm,
                        "smuggled_harm": d.smuggled_harm,
                        "smuggled_through": d.smuggled_through,
                        "per_axis_diff": {k: v for k, v in d.per_axis_diff.items() if v},
                    }
                    for d in self.diffs
                ),
                key=lambda r: r["label"],
            ),
        }


def score_smuggle_throughs(pairs) -> SmuggleReport:
    diffs = [diff_paraphrase(p) for p in pairs]
    by_cat: dict[str, dict] = {}
    for d in diffs:
        cat = by_cat.setdefault(d.leak_category, {"pairs": 0, "smuggled": 0})
        cat["pairs"] += 1
        cat["smuggled"] += int(d.smuggled_through)
    return SmuggleReport(
        pairs=len(diffs),
        smuggled_through=sum(1 for d in diffs if d.smuggled_through),
        by_category=by_cat,
        diffs=diffs,
    )
