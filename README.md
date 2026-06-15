# The Nyx Engine

A multi-agent narrative game engine where competing AI personas — the Children of Nyx from Greek mythology — orchestrate a choose-your-own-adventure experience built on friction, not compliance.

The game doesn't serve you. It tests you.

---

## What Is This?

Nyx Engine is a text-driven CYOA game where a roster of autonomous AI agents collaborate and conflict to shape a living narrative. Each agent has a mythological role, a competing agenda, and a voice. A central **Nyx Kernel** resolves their disputes through a strict conflict hierarchy, producing emergent stories that feel authored — not generated.

Players make choices. The Fates judge them. A soul accumulates weight across four moral vectors. At the threshold turn, the engine assigns a tragic flaw based on a childhood of decisions. Death is permanent. Legacy echoes forward.

## Architecture

### Three Layers, Nine Live-Turn Agents

| Layer | Role | Agents |
|-------|------|--------|
| **Moirai** (Determinism) | Story truth, state validity, death | **Clotho** (prose weaver), **Lachesis** (state evaluator + RAG), **Atropos** (death arbiter) |
| **Adversaries** (Friction) | Anti-exploit karma, chaos injection | **Nemesis** (hubris punisher), **Eris** (chaos RNG) |
| **Gatekeepers** (Interface) | Latency masking, post-death, validation | **Hypnos** (loading mask prose), **Chronicler** (memory compression), **Momus** (NER validator), **Sophia** (semantic judge) |

Beyond the live turn, the **Morpheus ladder** (autonovel ↔ Nyx) adds two more organs: **Morpheus** (the Re-Outliner — plants and pays narrative promises across a life) and **Scribe** (binds a finished life into a typeset book). See `backend/MORPHEUS.md`.

The **Nyx Kernel** orchestrates all agents through a unified resolve pipeline and resolves conflicts via a strict priority hierarchy:

1. **Lachesis** (state validity) — overrides all
2. **Atropos** (death) — cannot be blocked
3. **Nemesis vs Eris** — hubris index tiebreaker
4. **Clotho** (prose only) — lowest priority

### Soul Vectors

Every player action shifts four moral dimensions:

- **Bia** (Force) — violence, dominance, wrath
- **Metis** (Cunning) — deception, strategy, intellect
- **Kleos** (Glory) — fame-seeking, boasting, spectacle
- **Aidos** (Shame) — restraint, stealth, humility

At a threshold turn, the dominant vector determines the player's **hamartia** (tragic flaw) — Wrath, Hubris, Vanity, or Cowardice — which reshapes the narrative permanently.

### Key Math

- **Soul Imbalance**: `I = max(vectors) − min(vectors)`. Imbalance ≥ threshold sharpens Nemesis's prophecy — who you are determines how it ends. Punishment requires *abuse* signals (exploit patterns, oath hypocrisy, runaway suspicion or faction heat); a committed character is not an exploit.
- **Pressure Evolution**: seven deterministic pressures (suspicion, scarcity, wounds, debt, faction heat, omen, exploit) evolve from action patterns each turn. Stability breeds chaos: every quiet turn raises Eris's strike probability.
- **Doom Staging**: death arrives in installments. A sealed doom advances one stage per turn; Atropos cuts at the final stage. Broken oaths are inescapable; mortal wounds and manhunts can still be answered before they mature.
- **Scene Clocks**: unresolved situations tick toward firing when the Fates strike, at chapter crises, and when the player coasts. A fired clock's stakes become true — permanently.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Frontend | SvelteKit 5, Svelte 5 (runes), Tailwind CSS v4 |
| LLM Routing | LiteLLM (multi-provider) |
| Vector Store | ChromaDB (ephemeral or persistent) |
| Database | PostgreSQL via asyncpg (optional — runs without DB) |
| Streaming | Server-Sent Events (SSE) via sse-starlette |
| Image Gen | Black Forest Labs FLUX (sumi-e ink wash aesthetic) |

### Agent Model Assignments

| Agent | Default Model | Role |
|-------|--------------|------|
| Clotho | Claude Sonnet 4 | Literary prose generation |
| Lachesis | Mercury 2 | Fast state evaluation |
| Nemesis | Mercury 2 | Hubris judgment |
| Eris | Mercury 2 | Chaos injection |
| Hypnos | Claude Haiku 4.5 | Loading mask flavor text |
| Chronicler | Claude Haiku 4.5 | Memory compression |

**Atropos** and **Momus** run deterministically (Atropos uses Nemesis's model only for an optional narrative dead-end check); **Sophia**, **Morpheus**, and **Scribe** each have their own configurable model — see `backend/app/core/config.py`.

All agents support a `mock` mode for development — no API keys required to run the full game loop.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) PostgreSQL for persistence
- (Optional) API keys for LLM providers

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add API keys, or leave empty for mock mode
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend proxies `/api` requests to `localhost:8000` automatically.

### LAN Play

```bash
cd frontend
npm run dev -- --host
```

Access from any device on your network at `http://<your-ip>:5173`.

## Testing

```bash
cd backend
pytest
```

The backend test suite covers every agent, the kernel resolve pipeline, conflict resolution, math services, oath detection, hamartia assignment, doom staging, scene clocks, the adult director, memory compression, the epoch state machine, the Morpheus ladder (promises, beats, the Scribe, the Assayer), the visual-plate rails, and the player-safety floor.

The suite is hermetic: every agent is forced into mock mode with zero simulated latency, so tests run offline, deterministically, and in well under a minute — regardless of what models and keys are configured in `.env`.

## Project Structure

```
backend/
  app/
    agents/        # agent implementations (mock + LLM modes)
    api/           # FastAPI routes (SSE streaming, REST)
    core/          # Nyx Kernel, conflict resolver, config, prompt templates
    db/            # PostgreSQL persistence (optional)
    schemas/       # Pydantic v2 models (ThreadState, agent responses)
    services/      # Game math, oath engine, hamartia engine, chronicler
  tests/           # hermetic pytest suite (mock mode, offline)
  prompts/         # Externalized agent prompt templates

frontend/
  src/
    lib/
      components/  # TitleScreen, Incarnation, TheThread, Console,
                   # SoulLedger, TheOracle
      stores/      # Svelte 5 rune stores (engine, vestibule)
      types/       # TypeScript interfaces
      utils/       # SSE client, helpers
    routes/        # SvelteKit pages
```

## Game Flow

1. **The Tapestry** — Ambient title screen with ash particles, a golden thread, and ghost echoes of past lives
2. **Incarnation** — Diegetic character creation (name, gender). No menus. The Fates ask directly.
3. **Childhood** (Phases 1-3) — Button-driven choices accumulate soul vectors. The engine watches.
4. **The Fork** (Phase 4) — Hamartia assigned from dominant vector. Free-text input unlocks.
5. **The Thread** — Full narrative gameplay. The Adult Director stages each scene from live state: dooms, clocks, oaths, pressures, the flaw. Agents compete. Nemesis watches.
6. **Death** — Permanent, and staged. A doom seals, escalates turn by turn, then Atropos cuts. The thread joins the Tapestry.

## Design Philosophy

- **Friction over compliance.** The game resists the player. Nemesis punishes exploitation. Eris injects chaos into winning streaks.
- **Emergent, not scripted.** No branching story tree. Eight agents with competing agendas produce narrative through conflict resolution.
- **Death is real.** No saves. No reloads. Dead threads become ghost echoes on the title screen for future incarnations.
- **The math is the story.** Soul vectors, hubris indices, and narrative stability integrals aren't hidden mechanics — they're the mythology made computational.

## License

All rights reserved. This project is not open source.
