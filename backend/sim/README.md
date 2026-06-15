# The Consequence Calibration Harness (`backend/sim/`)

A **deterministic, offline** life-simulation harness that turns the north
star — *friction over compliance* — from an assertion into a **measurement**.
It drives many scripted + adversarial lives through the real `NyxKernel` in
mock mode to death-or-cap and emits friction-metric distributions as a
checked-in regression artifact, plus a red-team that measures how easily the
keyword consequence layer is evaded.

This is a **measurement sprint**: it changes no game behaviour. `app/` never
imports `sim/` (asserted by a test). The only edits outside `sim/` are
additive, default-valued config settings the game path never reads.

## The optimization target is FRICTION — never retention

Every metric here exists to answer one question: *does a player who games the
engine reliably meet consequence, and does committed play reliably go
unpunished?* Tune the engine's constants toward **exploit precision/recall**,
**doom-escape rate**, **death-cause mix**, and **keyword smuggle-through** —
**never** toward player retention, satisfaction, or session length. A move
that "improves" a metric by softening the fiction (punishing committed play to
pump recall, or loosening detection into compliance) is a **regression**, and
the locked compliance-floor corpus (`legit_*` lives) exists to fail it.

## Running it

```
# From backend/, with the venv active:
python -m sim.emit_artifact          # regenerate baseline.friction.json
python -m pytest tests/test_sim_harness.py -q
```

`baseline.friction.json` is the regression artifact. A reviewer who touches any
consequence threshold (Nemesis abuse gate, doom thresholds/escapes, the
exploit curve, clock magnitudes, the Momus cutoffs) sees a visible diff here.
It regenerates **byte-identically** from the same seeds (a test enforces this).

## How a life is driven (determinism)

`run_life(script)` is self-contained and offline:

- **RNG state is saved and restored** around every life, so the global cursor
  any later test sees is byte-identical to a no-sim run (no suite poisoning).
- `random.seed(script.seed)` makes the mock pools reproducible.
- For `eris_off` scripts the **Eris chaos gate is patched off**. Eris is the
  *only* agent that injects RNG into *measured* state (Nemesis is RNG-free
  threshold reads, oaths/doom are deterministic, and the mock prose pools that
  use `random.choice` don't touch the trace), so an Eris-off corpus is
  byte-stable regardless of background-task scheduling. Morpheus/Scribe are
  drained every turn for good measure.
- `NyxRAGStore` is swapped for a no-op `NullRag` **before** any kernel is
  built, so `chromadb.Client()` is never constructed and no ONNX embedding
  model loads. (`rag_context` may still carry the mock Lachesis's deterministic
  combat summaries — that content is offline and reproducible, and in mock it
  feeds only paths that no-op.)
- `worlds_dir` is pinned to the frozen 4-cartridge copy in `worlds_frozen/`
  and the registry reloaded, so world selection can't drift with the repo.

It reuses the Assayer's `compute_verdict` (never reinvents the verdict) and
reconstructs the **death-cause bucket from the trace** (doom snapshots +
terminal vectors + the configured death keywords) — never from the free-text
`death_reason`, so a mock prose variant can never move a metric.

## Ground truth is hand-authored (non-tautology)

`is_exploit_turn` labels and the `ParaphrasePair`s are written from *in-fiction
intent*, never derived from the engine's predicates. That's what lets the
harness register the leaks the engine misses: the corpus carries a
**semantic-repeat** life (paraphrased thefts the exact-string repeat term never
catches), so `exploit_recall < 1.0` **by construction** — a perfect recall
would mean the metric is just string-equality agreeing with itself.

## Known calibration findings (what the harness already surfaced)

These are **descriptive** ("under the current constants"), not normative —
v1 ships no authored target distribution. They are the retuning leads the
*next* sprint acts on (this sprint does not retune anything):

- **Escapable dooms have a ~0% escape rate.** The staged window
  (`stage 1 → 2 → 3` over two turn-tops) gives only one actionable recovery
  turn, and one recovery (`wounds −0.8`, `faction_heat −0.4`) cannot cross the
  escape threshold from the `≥ 9.0` trigger. The `wounds_escape_try` life dies
  anyway.
- **Exploit recall ≈ 0.56.** The engine misses genuine exploits — the
  pre-`exploit ≥ 2` lag and, decisively, any *paraphrased* repeat.
- **Keyword smuggle-through ≈ 100%.** Every authored paraphrase evades the
  consequence layer entirely (`per_axis_diff` shows which branch leaked). The
  rate is a **lower bound** conditioned on the authored corpus — there is no
  fuzzing/search (the same author writes the attack, paraphrase, and label).

## Deliberate non-goals (so future devs don't engineer fallbacks)

- **No retuning.** This sprint measures the threshold map; changing constants
  is a separate follow-on the baseline informs.
- **No detector hardening.** Generalizing pressure detection past keywords
  re-routes `director._select_driver` (higher paraphrase pressures cross the
  loudest-pressure threshold sooner) — an explicitly **multi-axis** sprint.
- **No adversarial search / fuzzing**; **no semantic betrayal oracle** (the
  punishment-reframe class is a tautology against token detectors and folds
  into the keyword leak — that needs the carved-out LLM-judge layer).
- **Mock-only.** The baseline is regression-detection for mock decision-making,
  **not** production-LLM ground truth. Buckets unreachable in mock
  (`dead_soul`, `clock`, `narrative_dead_end`, `faction_heat` within the cap)
  are simply absent — they are not simulated.
- **`__capped__` is a labelled measurement bucket, not a death** (the turn cap
  is a documented parameter). Driving the real kernel **executes**
  `director._select_driver` as a side effect — the carve-out means the harness
  never *edits* it, not that it never *runs* it; the baseline bytes are jointly
  a function of pressure thresholds **and** routing.

See `backend/MORPHEUS.md` for the broader organ conventions.
