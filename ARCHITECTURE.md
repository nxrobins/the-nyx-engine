# The Nyx Engine — Architecture

This document is the contributor-facing map of how the engine is built. The
[README](README.md) is the pitch; this is the wiring.

## North star

> **Friction over compliance — the game tests the player.**

The engine exists to let an AI author *tragedy*. Its defining design choice is
**authority inversion**: the prose model (Clotho) holds the **lowest** authority,
and a layer of deterministic math decides what is actually true. A fluent model
cannot talk its way out of a consequence, and neither can the player. Death is
permanent; legacy echoes forward, name-independently.

Three properties fall out of that and are treated as non-negotiable invariants:

1. **The determinism gradient.** The consequence layer (`app/services/*`,
   `app/core/*` math) never calls a model mid-turn and never imports the agent
   tier. This is enforced as a build-time test (see below), not a convention.
2. **Permanence.** A death, once the deterministic tiers commit to it, stands. A
   self-destruction-framed death is additionally exempt from the one mercy valve
   (Eris, below).
3. **Name-independence.** A life's legacy is keyed by `thread_stamp =
   player_id:run`, never by the player's display name, so renaming changes nothing.

## The three layers and the agents

Eleven agents (the Children of Nyx) collaborate and conflict; the **Nyx Kernel**
(`app/core/kernel.py`) orchestrates them and a strict resolver settles disputes.

| Layer | Mandate | Agents |
|-------|---------|--------|
| **Moirai** — Determinism | story truth, state validity, death | **Clotho** (prose, lowest authority), **Lachesis** (state/validity + RAG), **Atropos** (death) |
| **Adversaries** — Friction | anti-exploit karma, chaos | **Nemesis** (imbalance punishment + prophecy), **Eris** (chaos RNG, scales with stability) |
| **Gatekeepers** — Interface | latency masking, memory, validation | **Hypnos** (dreams at epoch boundaries), **Chronicler** (memory compression), **Momus** (deterministic prose validator), **Sophia** (semantic judge) |

Beyond the live turn, the **Morpheus ladder** adds two organs — **Morpheus**
(the Re-Outliner) and **Scribe** (the Bookbinder) — described later.

Every agent ships a **mock fallback**, so the entire game loop runs keyless and
offline. Model assignments live in `app/core/config.py`.

## The conflict hierarchy

When agents return conflicting flags, the resolver (`app/core/resolver.py`)
settles them by a strict tier order — never a vote:

1. **Lachesis (validity)** — an invalid action mutes everything else.
2. **Atropos (finality)** — `terminal_state` overrides all *except* the Eris miracle.
3. **Nemesis vs Eris** — tiebroken by `W_c = imbalance_score − nemesis_threshold`
   (a more imbalanced soul earns punishment; a balanced one can earn a chaos break).
4. **Clotho (prose)** — zero logical authority; it only *formats* the winner.

**The Eris miracle valve:** a balanced soul that draws a chaos roll can have a
death deferred *for one turn* — except a self-destruction-framed death, which is
never miracled (permanence). Eris has a hard `0.02` chance floor, so any test that
asserts a death must pin `app.agents.eris.random.random → 0.999` to silence it
(`eris_chaos_probability=0.0` alone does not).

## A turn's lifecycle

`kernel._resolve_turn(action)` runs the deterministic game math, *then* hands a
fully-decided outcome to Clotho to narrate, *then* validates the prose:

1. **Lachesis** evaluates action validity and proposes state/vector deltas.
2. Apply vector deltas; at **turn 10 the hamartia forks** (a dominant soul vector
   becomes a tragic flaw — or "Unformed" resolves at the Fork).
3. **Doom progression** — an active doom advances one stage (or lifts if escaped).
4. The **Promise Ledger** keeps its books (Morpheus, below).
5. **Oaths** are detected → parsed → verified against the action.
6. **Parallel agent evaluation** (Nemesis, Eris, Atropos, …).
7. **Conflict resolution** via the tier hierarchy above.
8. Apply Eris chaos / Nemesis penalty; store prophecy; an **unpaid promise** spikes
   omen; **runaway pressures** can seal an escapable doom; a long undoomed thread
   eventually bends toward an **old-age** doom; **scene clocks tick**; the present
   **cast remembers** what the player did to them, and a deeply betrayed NPC **leaves**.
9. **Clotho** narrates the already-decided outcome.
10. **Momus** validates the prose for hallucinations (naming the dead/absent,
    contradicting canon); a single lapse commits a corrected line, several trigger a
    full regenerate. `_finalize_turn` then persists.

The consequence economy is fully settled by step 8. Clotho cannot change what
happened — only how it reads.

## Key systems

- **Soul vectors** (`services/soul_math.py`) — `metis / bia / kleos / aidos`, each
  0–10. `imbalance = max − min` drives Nemesis; all ≤ 1 is a dead soul; any = 10 is
  a milestone (a BFL image).
- **Pressure engine** (`services/pressure.py`) — suspicion, scarcity, wounds, debt,
  faction-heat, omen, and an `exploit_score` that punishes repeated actions.
- **Oaths** (`services/oath_engine.py`, `oath_parser.py`) — deterministic
  detect/parse/verify; a broken oath seals a lethal doom.
- **Doom** (`services/doom.py`) — staged death. A broken oath is an inescapable
  3-stage doom; mortal wounds / manhunt are escapable via pressure-decay routes.
  Atropos cuts only when a doom matures — death arrives in installments.
- **World seeds & cartridges** (`core/world_seeds.py`, `schemas/cartridge.py`,
  `core/world_registry.py`) — worlds are either built-in seeds or authored
  `*.nyx-world.json` cartridges loaded fail-loud-skip; `select_world` picks
  deterministically by `min(sha256(player_id:run:world_id))`.
- **Director** (`core/director.py`) — childhood (turns 1–9) runs authored epoch
  beats with vector-mapped choices; adulthood (turn 10+) is procedurally composed
  into 3-turn chapters, with a deterministic driver priority (doom > clock > oath >
  pressure > … > the world itself).

## The determinism gradient, as a test

`tests/test_architecture.py` parses the import graph with `ast` and asserts that
the guarded consequence modules import nothing from `app.agents.*` /
`app.services.llm` / `litellm`, and that `litellm` has exactly one choke point
(`services/llm.py`). The prose layer physically cannot reach into what decides
truth — and a future change that tries fails the build.

## The Morpheus ladder (autonovel ↔ Nyx)

A four-organ pipeline connected to the sibling `autonovel` project as a **data
contract, not code** (neither repo imports the other; the `WorldCartridge` /
`PlayVerdict` schemas are the seam):

1. **Worldsmith** — `autonovel` compiles a grounded world into a cartridge that
   passes Nyx's playability gate.
2. **Re-Outliner + Ledger** (`agents/morpheus.py`, `services/promise_engine.py`,
   `services/beat_gate.py`) — plants and pays narrative **promises** that cite
   *lived* turns; accidents become foreshadowing, and dreams (Hypnos) tell the truth.
3. **Scribe** (`agents/scribe.py`, `services/bookbinder.py`) — binds a finished
   life into a typeset **book**; `GET /library` serves the shelf.
4. **Assayer** (`services/assayer.py`) — distills a finished thread into a
   deterministic `PlayVerdict` (no LLM judges a life), feeding world fitness and the
   next generation. The prior life's book circulates into the next via the
   `thread_stamp`-keyed **ouroboros** lookup.

See [`backend/MORPHEUS.md`](backend/MORPHEUS.md) for the contract details.

## The Vigil — player safety

A duty-of-care layer for the **real human**, never the fiction (see
[`backend/SAFETY.md`](backend/SAFETY.md)). It governs *signposting-to-real-help* and
*privacy*; it never softens the character's friction. Phase 1 (always on) makes
self-destruction deaths non-miracleable and redacts flagged crisis input from every
durable store. Phase 2 (built, **gated** behind `welfare_copy_reviewed=False`) adds
the crisis-routing surface — inert until a human reviewer signs the words.

## Tech stack & running it

Python / FastAPI + Pydantic v2; LiteLLM; ChromaDB for RAG; optional SQLite/Postgres.
SvelteKit 5 + Tailwind v4 frontend over SSE (a 3-phase mechanic → prose → state
protocol). Per-UUID session kernels.

```bash
# Backend (mock mode = keyless, free)
cd backend && pytest                  # hermetic suite, runs offline
uvicorn main:app --port 8000          # the root shim, not app.main

# Frontend
cd frontend && npm install && npm run dev
npm test && npx svelte-check          # pure-logic unit tests + types
```

Dependencies live in `backend/requirements.txt` (the `pyproject.toml` declares
none). The test suite forces every agent into mock mode with zero simulated
latency, so it is deterministic and needs no API keys.
