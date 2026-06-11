# Morpheus — the autonomous author that works the gaps

Morpheus is the engine's authoring daemon: it generates and revises the *telling*
and the *plan* of a life, but only where the player is not, and it is
constitutionally forbidden from touching what the player did. It is built as a
ladder of organs that connect to the live engine through **typed, versioned,
gated artifacts** — never through each other's code.

P1 (the World Compiler) is the first rung. It ships now. P2–P4 are sketched here
so they reuse P1's conventions instead of inventing their own.

---

## The boundary conventions (established by P1, reused by all organs)

1. **Organs connect through artifacts, not imports.** The only thing that crosses
   a boundary is a validated file. autonovel never imports Nyx; Nyx never imports
   autonovel. The contract is the JSON schema, vendored on the producer side.

2. **The consumer owns the schema; the producer owns the quality gate.** Nyx
   defines what *valid* means (`app/schemas/cartridge.py`, emitted as
   `worlds/world_cartridge.schema.json`). autonovel decides what *good* means (its
   playability/slop gate). Validity is enforced at load; quality at authoring.

3. **Every artifact carries a provenance/validity stamp** — `cartridge_version`,
   `world_id`, `source_hash`, `generated_by`. Unknown versions fail closed.

4. **Schema lives in a per-artifact module.** `schemas/cartridge.py` today; P2's
   beat-sheet and promise-ledger get siblings (`schemas/beat_sheet.py`,
   `schemas/ledger.py`).

5. **Loaders are fail-loud-per-file, skip-invalid, never-crash.** One malformed
   artifact can never disable its siblings or the deterministic fallback. See
   `core/world_registry.py` for the reference implementation.

6. **Every consumption point has a deterministic fallback.** The registry falls
   back to the in-code builtins (`world_seeds.WORLD_SEEDS`); the Director already
   falls back to procedural beats; Hypnos falls back to its mock-dream pool.
   Morpheus can be slow, stale, or dead and the game still plays — exactly the
   game that exists without it.

7. **Artifacts are published atomically and read from frozen snapshots.** Writers
   temp-write + `os.replace`; readers never observe a partial file and never read
   live engine state. (See the Constraints & Fallbacks matrix in the P1 plan.)

8. **The immune system gates the Author too.** Generated artifacts pass the same
   deterministic screens (anti-slop, anti-mysticism, schema) the live agents do.
   Momus mocks Morpheus.

**The one inviolable law:** Morpheus may revise the *telling* and author the
*future*; it may never change a *lived fact*. The factual chronicle is
Lachesis's property — permanent and unretconnable. The moment revision can touch
lived events, consequence dies and the engine becomes the sycophant it was built
to defeat.

---

## The organs

### P1 — The Worldsmith (SHIPPED)
Generates a gated `*.nyx-world.json` cartridge from an autonovel foundation. Nyx
loads it through `core/world_registry.py` and incarnates it via the existing
`bootstrap_canon`. Infinite gated worlds replace the four hand-authored seeds.

- Schema: `app/schemas/cartridge.py` → `worlds/world_cartridge.schema.json`
- Loader/selector: `app/core/world_registry.py` (`select_world_seed`)
- Producer: `autonovel/gen_nyx_cartridge.py`

### P2 — The Re-Outliner + Promise Ledger (SHIPPED)
Between epochs, behind the Hypnos dream-curtain, re-outlines the next epoch from
the *lived* one: a typed Beat Sheet plus a Promise Ledger of plants/payoffs that
turns player accidents into foreshadowing. The procedural floor (authored
childhood beats / the Adult Director) remains; the authored beat sheet is the
ceiling — same kernel slot, silent per-beat fallback. Dreams read the ledger.

- Contracts: `app/schemas/morpheus.py` (Promise, BeatSheet w/ validity stamps +
  per-beat machine-checkable preconditions, MorpheusSnapshot)
- Bookkeeping: `app/services/promise_engine.py` (audit/apply/pay/render; the
  constitutional check — plants must cite lived turns — lives here)
- The gate: `app/services/beat_gate.py` (harvest-time Sprint-10 lint;
  consume-time `preconditions_hold` against live canon)
- The agent: `app/agents/morpheus.py` (mock = deterministic floor-enrichment;
  real = one structured call + one informed retry; None → the floor plays)
- Lifecycle: kernel fires at every RESOLUTION with a frozen snapshot, harvests
  at the top of the next turn (stamps → gate → ledger updates), consumes
  per-beat with validate-at-the-moment-of-use, cancels on reset/death.
- Teeth: abandoned promises raise omen; Nemesis reads active promises for
  ironic targeting; Clotho gets THE LOOM REMEMBERS in stratified context.

### P3 — The Scribe (LATER)
Write-behind biography: drafts each lived epoch as a chapter in a life-voice
discovered at the Fork, validated against the factual chronicle by the same Momus
machinery. At death: final chapters + one review pass + typeset → a book that
enters the Tapestry as a library a descendant can read in-world.

### P4 — The Assayer (LATER)
Post-life evaluation retargeted from "good prose" to "good *life*" (clock
utilization, choice entropy, soul-arc shape). Worlds gain genealogy and fitness;
the Worldsmith evolves the next generation against the player as the invariant —
the state-space evolution loop, with the human as the gate.

---

## Topology

Morpheus is a background worker, never in the turn path. The kernel publishes
events (`epoch_complete`, `thread_severed`) carrying frozen state snapshots;
Morpheus consumes them and writes artifacts the kernel polls at its (already
fallback-guarded) consumption points. Per-thread it processes serially (causality
preserved); across threads it parallelizes freely. It holds no tier in the
resolver hierarchy — it is upstream advice, gated like everything else.
