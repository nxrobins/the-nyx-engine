"""The Consequence Calibration Harness — self-tests.

Proves the harness is hermetic, deterministic, sound (non-tautological),
suite-safe, and friction-pinned (the compliance backdoor is closed). Runs
inside the normal suite under the autouse hermetic fixture (mock models,
zero latency, tmp books/assays); run_life self-contains the rest (RNG
save/restore, Eris off, NullRag swap, frozen worlds).
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import random

import pytest

_SIM_DIR = pathlib.Path(__file__).resolve().parent.parent / "sim"


def _imports_module(path: pathlib.Path, module: str) -> bool:
    """True if the file has a real import STATEMENT for `module` (not prose)."""
    tree = ast.parse(path.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == module or a.name.startswith(module + ".") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == module or (node.module or "").startswith(module + "."):
                return True
    return False

from sim import emit_artifact
from sim.corpus import PARAPHRASE_PAIRS, SCRIPTS
from sim.life_script import LifeScript, ParaphrasePair
from sim.metrics import (
    build_report,
    classify_death,
    doom_economy,
    exploit_score,
)
from sim.outcome import DEATH_BUCKETS
from sim.red_team import diff_paraphrase, score_smuggle_throughs
from sim.runner import FROZEN_WORLD_IDS, run_corpus, run_life

_PUNISH = {"punishment", "lethal_punishment"}


def _by_label(label: str) -> LifeScript:
    return next(s for s in SCRIPTS if s.label == label)


def _fingerprint(outcome) -> str:
    """A deterministic, byte-comparable projection of a LifeOutcome."""
    return json.dumps(
        {
            "label": outcome.label,
            "world_id": outcome.world_id,
            "terminal": outcome.terminal,
            "capped": outcome.capped,
            "died_turn": outcome.died_turn,
            "final_vectors": outcome.final_vectors,
            "verdict": outcome.verdict.model_dump() if outcome.verdict else None,
            "turns": [dataclasses.asdict(t) for t in outcome.turns],
        },
        sort_keys=True,
    )


# ---------------------------------------------------------------------------
# Determinism (CAL-E2)
# ---------------------------------------------------------------------------

class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_script_same_outcome(self):
        s = _by_label("wounds_fail_stone")
        a = _fingerprint(await run_life(s))
        b = _fingerprint(await run_life(s))
        assert a == b

    @pytest.mark.asyncio
    async def test_neighbor_life_does_not_perturb(self):
        # A different life run in between must not change the first's outcome —
        # proves no background task / RNG draw crosses a life boundary.
        target = _by_label("oath_break_stone")
        first = _fingerprint(await run_life(target))
        await run_life(_by_label("exploit_spam_shadow"))
        second = _fingerprint(await run_life(target))
        assert first == second

    @pytest.mark.asyncio
    async def test_baseline_regenerates_byte_identical(self):
        artifact = await emit_artifact.build_artifact()
        regenerated = emit_artifact.serialize(artifact)
        committed = emit_artifact._BASELINE.read_text(encoding="utf-8")
        assert regenerated == committed, "baseline drift — a threshold moved or the corpus changed"


# ---------------------------------------------------------------------------
# Suite isolation (CAL-E3)
# ---------------------------------------------------------------------------

class TestSuiteIsolation:
    @pytest.mark.asyncio
    async def test_global_rng_cursor_restored(self):
        before = random.getstate()
        await run_life(_by_label("exploit_spam_shadow"))
        assert random.getstate() == before


# ---------------------------------------------------------------------------
# Hermeticity + world pinning (CAL-E1)
# ---------------------------------------------------------------------------

class TestHermeticity:
    @pytest.mark.asyncio
    async def test_each_life_draws_its_expected_world(self):
        for s in SCRIPTS:
            o = await run_life(s)
            assert o.world_id == s.expected_world_id
            assert o.world_id in FROZEN_WORLD_IDS

    @pytest.mark.asyncio
    async def test_no_real_rag_store_was_used(self):
        # run_life raises if kernel.rag isn't NullRag; a clean run proves it.
        o = await run_life(_by_label("legit_light"))
        assert o.terminal is False


# ---------------------------------------------------------------------------
# Scenario correctness (CAL-E6)
# ---------------------------------------------------------------------------

class TestScenarios:
    @pytest.mark.asyncio
    async def test_every_scripted_death_hits_its_bucket(self):
        for s in SCRIPTS:
            if s.expected_death_bucket is None:
                continue
            o = await run_life(s)
            assert classify_death(o) == s.expected_death_bucket, s.label

    @pytest.mark.asyncio
    async def test_broken_oath_doom_matures_on_schedule(self):
        o = await run_life(_by_label("oath_break_stone"))
        # find the broken_oath doom's started_turn from the trace
        started = next(t.doom.started_turn for t in o.turns if t.doom.cause == "broken_oath")
        max_stage = next(t.doom.max_stage for t in o.turns if t.doom.cause == "broken_oath")
        assert o.died_turn == started + max_stage - 1   # derived, not hardcoded +3
        assert classify_death(o) == "broken_oath"

    @pytest.mark.asyncio
    async def test_inescapable_doom_never_smuggles_through(self):
        outcomes = await run_corpus(SCRIPTS)
        econ = doom_economy(outcomes)
        assert econ["inescapable_smuggle"] == 0
        assert econ["inescapable_lives"] >= 1   # the corpus actually exercises it


# ---------------------------------------------------------------------------
# Metric soundness — non-tautology + no fold leak (CAL-E4 / CAL-E5)
# ---------------------------------------------------------------------------

class TestMetricSoundness:
    @pytest.mark.asyncio
    async def test_exploit_recall_below_one_by_construction(self):
        # The semantic-repeat corpus contains genuine exploits the engine's
        # string-equality predicate misses; recall MUST be < 1.0, else the
        # metric is tautological (just string-equality agreeing with itself).
        outcomes = await run_corpus(SCRIPTS)
        score = exploit_score(outcomes)
        assert score.false_negative >= 1
        assert score.recall < 1.0

    def test_metrics_does_not_import_the_detector(self):
        # metrics scores against hand labels; importing the detector would risk
        # a tautology. (ast, so the docstring mention doesn't false-positive.)
        assert not _imports_module(_SIM_DIR / "metrics.py", "app.services.pressure")

    def test_red_team_calls_but_does_not_copy_the_detector(self):
        # red_team CALLS the real detector (the point) but copies none of it.
        assert _imports_module(_SIM_DIR / "red_team.py", "app.services.pressure")
        src = (_SIM_DIR / "red_team.py").read_text("utf-8")
        assert "_VIOLENT_WORDS" not in src and "_DECEPTIVE_WORDS" not in src  # never COPIES
        assert "_normalize_action" not in src

    def test_identical_pair_yields_zero_keyword_diff(self):
        d = diff_paraphrase(ParaphrasePair("id", "steal the bread", "steal the bread", "deceptive", "x"))
        assert all(v == 0.0 for v in d.per_axis_diff.values())
        assert d.smuggled_through is False
        assert d.plain_harm == d.smuggled_harm

    def test_null_pair_yields_zero_keyword_diff(self):
        # Both miss every keyword token → only the (cancelling) repeat term.
        d = diff_paraphrase(ParaphrasePair("null", "ponder the road quietly", "reflect on the road calmly", "none", "x"))
        assert all(v == 0.0 for v in d.per_axis_diff.values())
        assert d.smuggled_through is False

    def test_known_keyword_leak_is_documented(self):
        report = score_smuggle_throughs(PARAPHRASE_PAIRS)
        assert report.smuggled_through >= 1   # the leak is real and tracked


# ---------------------------------------------------------------------------
# Bucket integrity (CAL-E6)
# ---------------------------------------------------------------------------

class TestBucketIntegrity:
    @pytest.mark.asyncio
    async def test_every_life_maps_to_exactly_one_closed_bucket(self):
        outcomes = await run_corpus(SCRIPTS)
        buckets = [classify_death(o) for o in outcomes]
        assert all(b in DEATH_BUCKETS for b in buckets)
        report = build_report(outcomes)
        assert sum(report.death_cause_mix.values()) == len(outcomes)   # no fall-through

    @pytest.mark.asyncio
    async def test_death_mix_doom_counts_agree_with_doom_economy(self):
        outcomes = await run_corpus(SCRIPTS)
        report = build_report(outcomes)
        econ = doom_economy(outcomes)
        mix = report.death_cause_mix
        inescapable = mix.get("broken_oath", 0) + mix.get("clock", 0)
        escapable = mix.get("wounds", 0) + mix.get("faction_heat", 0)
        assert inescapable == econ["inescapable_deaths"]
        assert escapable == econ["escapable_deaths"]


# ---------------------------------------------------------------------------
# The compliance backdoor is closed (CAL-E7)
# ---------------------------------------------------------------------------

class TestComplianceFloor:
    @pytest.mark.asyncio
    async def test_legitimate_lives_are_never_punished(self):
        # Committed-but-legitimate play MUST stay unpunished — independent of
        # the baseline artifact. Lowering the Nemesis abuse gate to pump recall
        # would punish these and fail here.
        legit = [s for s in SCRIPTS if s.legitimate]
        assert len(legit) >= 2
        for s in legit:
            o = await run_life(s)
            punished = [t.turn_number for t in o.turns if t.nemesis_type in _PUNISH]
            assert punished == [], f"{s.label} was punished on turns {punished}"

    @pytest.mark.asyncio
    async def test_no_false_positive_punishment(self):
        outcomes = await run_corpus(SCRIPTS)
        score = exploit_score(outcomes)
        assert score.false_positive == 0   # the engine never punished committed play
        assert score.precision == 1.0


# ---------------------------------------------------------------------------
# Measurement-only boundary (CAL-E8)
# ---------------------------------------------------------------------------

class TestMeasurementOnly:
    def test_app_never_imports_sim(self):
        app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
        offenders = []
        for path in app_dir.rglob("*.py"):
            text = path.read_text("utf-8")
            if "import sim" in text or "from sim" in text:
                offenders.append(str(path))
        assert offenders == [], f"app/ must never import the harness: {offenders}"
