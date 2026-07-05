"""The Nyx Kernel - Asynchronous Orchestrator v5.1 (Responsibility Split).

The central nervous system of the engine. Receives player input,
dispatches to agents in parallel, resolves conflicts, and produces
the final turn result.

v5.1 — Lachesis Responsibility Split (P1-002):
  Oath detection and hamartia assignment are now kernel-owned via
  dedicated service modules (oath_engine, hamartia_engine). Lachesis
  LLM output is treated as an optional enhancement; deterministic
  engines provide the guaranteed fallback. Steps 2b and 3 updated.

v5.0 — Kernel Decomposition (P0-003):
  The 10-step pipeline is split into three reusable methods:
    _resolve_turn()  — Steps 1-8: pure game math (Lachesis → resolver)
    _finalize_turn()  — Step 10+: post-prose bookkeeping (Momus → DB)
    _handle_death()   — Terminal path: epitaph + DB + death result
  process_turn() and process_turn_stream() are thin orchestration shells.

v4.0 additions (The Supremum Patch):
- Chronicler agent: recursive memory compression every 5 turns
- Stratified Context Builder: [Chronicle] + [Short-Term] + [Soul Mirror]
- Soul Mirror: style directives injected based on dominant vector ≥ 7.0

v3.0 additions:
- Director System (_get_turn_metadata) controls age, beat, UI mode per turn
- PostgreSQL persistence (optional) for players, threads, turns
- Death hook: awaited epitaph generation + DB persist
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator

from app.agents.atropos import Atropos
from app.agents.chronicler import Chronicler
from app.agents.clotho import Clotho, _parse_clotho_output
from app.agents.eris import Eris
from app.agents.hypnos import Hypnos
from app.agents.lachesis import Lachesis
from app.agents.momus import Momus
from app.agents.sophia import Sophia
from app.agents.morpheus import Morpheus
from app.agents.nemesis import Nemesis
from app.agents.scribe import Scribe
from app.core.config import settings
from app.core.director import select_adult_beat
from app.core.resolver import ConflictResolver, ResolvedOutcome
from app.core.world_registry import select_world
from app.core.world_seeds import format_world_context
from app.schemas.book import Chapter, ScribeSnapshot
from app.schemas.morpheus import BeatSheet, FloorBeat, MorpheusSnapshot
from app.schemas.state import (
    DeliberationTrace,
    LachesisResponse,
    MomusValidation,
    Oath,
    SceneOutcome,
    ThreadState,
    TurnResult,
)
from app.db import (
    ensure_player, create_thread, update_thread_death,
    create_turn, append_chronicle, append_factual_chronicle,
    get_dead_threads, get_last_ancestor,
)
from app.services import llm
from app.services.bfl import generate_image
from app.services.canon import (
    apply_environment_update,
    bootstrap_canon,
    client_safe_state,
    derive_environment_string,
    maybe_arrive_npcs,
    maybe_depart_npcs,
    relieve_clock,
    render_scene_snapshot,
    tick_scene_clocks,
    update_npc_relations,
)
from app.services.welfare import REDACTION_TOKEN, flags_sensitive_input
from app.services.doom import (
    advance_doom,
    begin_doom,
    doom_directive,
    maybe_begin_old_age_doom,
    maybe_begin_pressure_dooms,
)
from app.services.hamartia_engine import (
    determine_hamartia,
    get_hamartia_profile,
    get_life_voice,
)
from app.services.legacy import build_legacy_echo
from app.services.oath_engine import (
    detect_oath,
    is_verifiable_violation,
    verify_oaths,
)
from app.services.oath_parser import parse_oath_text
from app.services.assayer import compute_verdict, write_verdict
from app.services.beat_gate import gate_beat, preconditions_hold
from app.services.bookbinder import bind_book, list_books, write_book
from app.services.pressure import apply_pressure_delta, evolve_pressures, pressure_summary
from app.services.promise_engine import (
    ABANDONMENT_OMEN,
    active_promises,
    apply_ledger_updates,
    audit_ledger,
    mark_paid,
    render_ledger,
)
from app.services.rag import NyxRAGStore
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.kernel")


# ---------------------------------------------------------------------------
# Epoch State Machine + Director Metadata (Sprint 8)
# ---------------------------------------------------------------------------

# Age map: deterministic age per turn (childhood = turns 1-9)
_AGE_MAP: dict[int, int] = {
    1: 3, 2: 4, 3: 5,      # Epoch 1: toddler → early child
    4: 7, 5: 8, 6: 10,     # Epoch 2: school age
    7: 12, 8: 14, 9: 17,   # Epoch 3: adolescence
}

# Authored beat directives — one per turn, keyed by turn number.
# Each entry is (beat_position, directive) with epoch-specific narrative guidance.
# Sprint 10: Scene isolation + physical grounding + named-character mandates.
_TURN_BEATS: dict[int, tuple[str, str]] = {
    # ═══ EPOCH 1: THE HEARTH (ages 3-5) ═══
    1: ("SETUP",
        "NEW SCENE. The child is at home. A parent is present and doing "
        "something specific. Write a mundane domestic moment ALREADY IN "
        "PROGRESS: a meal, a chore, tending an animal, repairing something. "
        "Use the parent's NAME from the world context. The active situation "
        "should create background tension the child senses but doesn't "
        "understand. End by introducing a disruption: a sound, a visitor, "
        "something breaking."),

    2: ("COMPLICATION",
        "NEW SCENE. Time has passed since the last scene. The child is "
        "slightly older within this epoch. The disruption from the previous "
        "scene has consequences that are now visible. A NEW character enters "
        "the child's world (a neighbor, a stranger, another child). This "
        "person brings a problem or a revelation. Use NAMES. Reference "
        "the family and settlement from the world context."),

    3: ("RESOLUTION",
        "NEW SCENE. The conflict from this epoch reaches a breaking point. "
        "The child must act: protect someone, hide something, speak or stay "
        "silent. The choice should be physically concrete (not philosophical). "
        "Show the IMMEDIATE consequence: someone's expression changes, "
        "something breaks, a door closes. This epoch ends here. After this, "
        "the child will dream and wake into a new chapter of life."),

    # ═══ EPOCH 2: THE WORLD OUTSIDE (ages 7-10) ═══
    4: ("SETUP",
        "NEW SCENE. Years have passed. The child is now in the wider world "
        "beyond home: a market, a workplace, a gathering place. NEW "
        "characters: peers, authority figures, rivals. Establish the social "
        "hierarchy the child must navigate. The family's situation from "
        "Epoch 1 should have evolved (better or worse based on past choices). "
        "Ground the scene in a specific physical activity."),

    5: ("COMPLICATION",
        "NEW SCENE. Time has passed since the last scene. A relationship "
        "is tested: a friend demands loyalty, an authority figure is unfair, "
        "a secret is discovered. The stakes are social: reputation, "
        "belonging, safety. Someone SAYS something that changes things. "
        "Use DIALOGUE. Reference characters and locations by NAME."),

    6: ("RESOLUTION",
        "NEW SCENE. The social conflict reaches a crisis. The child must "
        "act publicly: others are watching. Whatever happens, people will "
        "remember. Show the IMMEDIATE consequence: how others react, what "
        "changes in the child's standing. This epoch ends here. After this, "
        "the child will dream and wake into adolescence."),

    # ═══ EPOCH 3: THE CRUCIBLE (ages 12-17) ═══
    7: ("SETUP",
        "NEW SCENE. Years have passed. The adolescent's body has changed. "
        "The world treats them differently. Establish a new environment "
        "where the adolescent has a role or responsibility (apprentice, "
        "laborer, student, soldier-in-training). Introduce a figure of "
        "authority or mentorship. Show the tension between who they were "
        "as a child and who they're becoming."),

    8: ("COMPLICATION",
        "NEW SCENE. Time has passed since the last scene. The authority "
        "figure or system the adolescent trusted fails them or betrays "
        "them. A rule is revealed to be a lie, a protector is revealed "
        "to be complicit, or a promise is broken. The adolescent must "
        "decide whether to submit or resist. Use DIALOGUE. The "
        "conversation should be the scene."),

    9: ("RESOLUTION",
        "NEW SCENE. The final night before adulthood. The adolescent "
        "faces an adult-sized decision with adolescent tools. Someone "
        "will be hurt no matter what they choose. A door closes forever. "
        "Show the IMMEDIATE consequence. After this, the player wakes "
        "into adulthood and the text box opens. Childhood is over."),
}


# Adulthood begins at turn 10 (epoch 4, age 18 — see _get_turn_metadata). Used by
# the lethal-clock childhood guard (WB-C1): a world's kill switch is inert until
# the player is an adult.
_ADULT_START_TURN = 10


def _doom_from_lethal_clock(state, fired_clock) -> bool:
    """A fired authored lethal clock begins an inescapable 3-stage doom — the
    single point where a world's clock can threaten a life.

    WB-C1: inert in childhood (turns 1-9) — bootstrap_canon, the only clock
    instantiation point, is always a childhood scene, so the age rule lives here.
    WB-C2: routes through `begin_doom` (staged; Atropos severs only at the final
    stage, Eris-miracle valve intact) — a world NEVER sets terminal or severs
    directly. Returns True iff a doom took hold.
    """
    if not fired_clock.lethal:
        return False
    if state.session.turn_count < _ADULT_START_TURN:
        return False
    return begin_doom(
        state,
        cause="clock",
        description=fired_clock.stakes,
        max_stage=3,
        escapable=False,
    )


def _get_turn_metadata(turn_count: int) -> tuple[int, int, str, str, str]:
    """Return (phase, age, ui_mode, beat_position, vignette_directive).

    Epochs 1-3 (turns 1-9): 3 turns each, buttons, deterministic age, authored beats.
    Epoch 4 (turns 10+): open mode, age increments from 18, no beat structure.
    """
    if turn_count <= 3:
        phase = 1
    elif turn_count <= 6:
        phase = 2
    elif turn_count <= 9:
        phase = 3
    else:
        phase = 4

    age = _AGE_MAP.get(turn_count, 18 + (turn_count - 10))

    if turn_count <= 9 and turn_count in _TURN_BEATS:
        ui_mode = "buttons"
        beat_position, directive = _TURN_BEATS[turn_count]
    else:
        ui_mode = "open"
        beat_position = "OPEN"
        directive = ""

    return phase, age, ui_mode, beat_position, directive


# ---------------------------------------------------------------------------
# Soul Mirror Directives (style injection based on dominant vector)
# ---------------------------------------------------------------------------

_SOUL_MIRROR: dict[str, str] = {
    "bia": (
        "STYLE DIRECTIVE (The World of Force): "
        "The world feels fragile and obstructive. Use verbs of impact — "
        "shatter, crack, split, crush. Surfaces resist and then give. "
        "Even stillness trembles with the threat of violence."
    ),
    "metis": (
        "STYLE DIRECTIVE (The World of Riddles): "
        "The world is a riddle with teeth. Use verbs of observation and "
        "dissection — peel, unravel, trace, measure. Every shadow hides "
        "a mechanism. Silence is a language the player reads fluently."
    ),
    "kleos": (
        "STYLE DIRECTIVE (The World of Witnesses): "
        "The world watches. Use verbs of display and echo — ring, blaze, "
        "carve, proclaim. Light seeks the player. Crowds are always near, "
        "even when absent — the weight of unseen eyes never lifts."
    ),
    "aidos": (
        "STYLE DIRECTIVE (The World of Shadows): "
        "The world retreats and conceals. Use verbs of withholding and "
        "fading — shrink, muffle, dim, fold. Borders blur. The player "
        "moves through the world like smoke, leaving no mark."
    ),
}


def _build_stratified_context(state: ThreadState) -> str:
    """Assemble the Stratified Context for Clotho's system prompt.

    Architecture (token-budget ~2,000 tokens total):
        TOP    — The Theology:  Literary Laws (already baked into CLOTHO_SYSTEM_PROMPT)
        MID    — The Chronicle: Mythic + Factual dual-track (long-term memory)
        ACTIVE — The Short-Term: Last 2 turns of raw prose (immediate continuity)
        BOTTOM — The Mirror:    Style directive from dominant soul vector

    Returns an assembled string that the kernel prepends to Clotho's system prompt.
    The Literary Laws live in CLOTHO_SYSTEM_PROMPT itself, so this function
    builds only the dynamic layers: Chronicle + Factual + Short-Term + Mirror.
    """
    sections: list[str] = []

    # ── TOP: The Origin (immutable birth lore) ────────────────────
    if state.world_context:
        sections.append(
            "═══ THE ORIGIN (Background Lore) ═══\n"
            "This is the world the player was born into. CRITICAL: Characters "
            "listed here may have DIED or situations may have CHANGED since "
            "birth. You MUST prioritize the FACTUAL RECORD and RECENT THREAD "
            "below for the current truth. The Origin is backstory, not current "
            "state.\n"
            f"{state.world_context}"
        )

    scene_snapshot = render_scene_snapshot(state)
    if scene_snapshot:
        sections.append(
            "═══ THE CANON NOW (Structured Scene Truth) ═══\n"
            "This is the current scene state. Treat it as canonical when prose, "
            "memory, or atmosphere would otherwise drift.\n"
            f"{scene_snapshot}"
        )

    if state.legacy_echoes:
        legacy_block = "\n".join(
            f"  • {echo.inherited_mark}: {echo.mechanical_effect}"
            for echo in state.legacy_echoes[:2]
        )
        sections.append(
            "═══ THE DEAD STILL SPEAK ═══\n"
            f"{legacy_block}"
        )

    sections.append(
        "═══ WORLD PRESSURE ═══\n"
        f"{pressure_summary(state)}"
    )

    # ── MID: The Chronicle (long-term mythic memory) ──────────────
    if state.chronicle:
        chronicle_block = "\n".join(f"  • {s}" for s in state.chronicle)
        sections.append(
            "═══ THE CHRONICLE (mythic history of this soul) ═══\n"
            f"{chronicle_block}"
        )

    # ── MID-2: Factual Record (state consistency memory) ──────────
    if state.factual_chronicle:
        factual_block = "\n".join(f"  • {s}" for s in state.factual_chronicle)
        sections.append(
            "═══ FACTUAL RECORD (state consistency — do not contradict) ═══\n"
            f"{factual_block}"
        )

    # ── MID-3: The Promise Ledger (Morpheus P2) ───────────────────
    ledger_block = render_ledger(state, state.session.turn_count)
    if ledger_block:
        sections.append(
            "═══ THE LOOM REMEMBERS (debts of the story) ═══\n"
            "These are promises the narrative has made. Weave quiet callbacks "
            "to planted ones; when a beat directive pays one, its consequence "
            "must land visibly in the scene.\n"
            f"{ledger_block}"
        )

    # ── ACTIVE: Last 2 turns of raw prose (short-term memory) ─────
    recent = state.prose_history[-2:] if state.prose_history else []
    if recent:
        recent_block = "\n\n---\n\n".join(recent)
        sections.append(
            "═══ RECENT THREAD (last scene — maintain continuity) ═══\n"
            f"{recent_block}"
        )

    # ── BOTTOM: The Soul Mirror (style directive) ─────────────────
    vectors = state.soul_ledger.vectors
    pairs = [
        ("metis", vectors.metis), ("bia", vectors.bia),
        ("kleos", vectors.kleos), ("aidos", vectors.aidos),
    ]
    dominant_name, dominant_val = max(pairs, key=lambda x: x[1])

    # Only inject mirror if the dominant vector is pronounced enough
    if dominant_val >= settings.soul_mirror_threshold:
        mirror = _SOUL_MIRROR.get(dominant_name, "")
        if mirror:
            sections.append(f"═══ THE SOUL MIRROR ═══\n{mirror}")

    if state.soul_ledger.hamartia_profile is not None:
        sections.append(
            "═══ THE FLAW HARDENS ═══\n"
            f"{state.soul_ledger.hamartia_profile.style_directive}"
        )

    # ── THE DOOM: staged death closes in (all phases) ─────────────
    doom_text = doom_directive(state)
    if doom_text:
        sections.append(
            "═══ THE DOOM CLOSES IN ═══\n"
            f"{doom_text}"
        )

    # ── MOMUS'S NOTES: craft corrections from last turn ───────────
    if state.craft_notes:
        notes_block = "\n".join(f"  • {n}" for n in state.craft_notes)
        sections.append(
            "═══ MOMUS'S NOTES (craft corrections — obey this scene) ═══\n"
            f"{notes_block}"
        )

    # ── DREAM BLEED: Hypnos residue (ephemeral, consumed once) ────
    if state.current_dream:
        sections.append(
            "═══ THE DREAM (Hypnos residue — reference abstractly, do not retell) ═══\n"
            f"{state.current_dream}"
        )

    if not sections:
        return ""

    return "\n\n".join(sections)


def _refresh_derived_environment(state: ThreadState) -> None:
    """Keep the UI-facing environment string aligned with canonical state."""
    derived = derive_environment_string(state)
    if derived:
        state.session.current_environment = derived


# ---------------------------------------------------------------------------
# Vector English Mapping (for mechanic toast display)
# ---------------------------------------------------------------------------

_VECTOR_ENGLISH: dict[str, str] = {
    "metis": "Cunning",
    "bia": "Force",
    "kleos": "Glory",
    "aidos": "Shadow",
}


def _english_deltas(deltas: dict[str, float]) -> dict[str, float]:
    """Convert internal vector names to English for frontend display."""
    return {_VECTOR_ENGLISH.get(k, k): v for k, v in deltas.items() if v != 0}


def _dominant_vector_english(deltas: dict[str, float]) -> str:
    """Return the English name of the dominant (largest absolute) delta."""
    if not deltas:
        return "Fate"
    dominant = max(deltas, key=lambda k: abs(deltas[k]))
    return _VECTOR_ENGLISH.get(dominant, dominant)


# ---------------------------------------------------------------------------
# TurnContext — the shared contract between _resolve_turn and the pipelines
# ---------------------------------------------------------------------------

@dataclass
class TurnContext:
    """Everything the pipeline needs after game-math resolution.

    Created by ``_resolve_turn()`` and consumed by both ``process_turn()``
    (sync Clotho) and ``process_turn_stream()`` (streaming Clotho).
    """
    turn: int
    phase: int
    ui_mode: str
    action: str
    outcome: ResolvedOutcome
    working_state: ThreadState
    lachesis_result: LachesisResponse
    stratified_context: str
    nemesis_desc: str
    eris_desc: str
    terminal: bool = False
    death_reason: str = ""
    # Sprint 8: Director metadata
    player_age: int = 3
    beat_position: str = "SETUP"
    vignette_directive: str = ""
    scene_outcome: SceneOutcome | None = None
    deliberation_trace: DeliberationTrace | None = None
    pressure_summary: str = ""
    # Non-terminal Atropos warning ("the Fates grow restless") — fed to Clotho
    atropos_warning: str = ""
    # The Vigil: this turn's action contains a self-destruction framing, so it
    # is redacted at every durable/observable store (privacy). The fiction's
    # math is computed from the real action and is unaffected.
    crisis_flagged: bool = False


def _persisted_action(ctx: "TurnContext") -> str:
    """Redact a welfare-flagged action before it reaches any durable store."""
    return REDACTION_TOKEN if ctx.crisis_flagged else ctx.action


# ---------------------------------------------------------------------------
# The Nyx Kernel
# ---------------------------------------------------------------------------

class NyxKernel:
    """The heart of the engine. Orchestrates all agents per turn."""

    def __init__(self) -> None:
        # Agents
        self.lachesis = Lachesis()
        self.atropos = Atropos()
        self.nemesis = Nemesis()
        self.eris = Eris()
        self.clotho = Clotho()
        self.hypnos = Hypnos()
        self.momus = Momus()
        self.sophia = Sophia()
        self.chronicler = Chronicler()
        self.morpheus = Morpheus()
        self.scribe = Scribe()

        # Systems
        self.resolver = ConflictResolver()
        self.rag = NyxRAGStore()

        # Session state (in-memory)
        self.state = ThreadState()

        # Morpheus P2: the pending re-outline task and the harvested sheet.
        # Both are advisory — every consumption point has its floor.
        self._morpheus_task: asyncio.Task | None = None
        self._beat_sheet: BeatSheet | None = None

        # Scribe P3: the write-behind biography. Chapters accumulate as
        # epochs are lived; death binds them. A missing chapter is a
        # shorter book, never an error.
        self._scribe_task: asyncio.Task | None = None
        self._chapters: list[Chapter] = []

        # DB persistence (set on initialize, cleared on reset)
        self._thread_id: int | None = None

    # ------------------------------------------------------------------
    # Turn 0: Initialize session with hamartia choice
    # ------------------------------------------------------------------

    async def initialize(
        self, hamartia: str, player_id: str = "usr_001",
        name: str = "Stranger", gender: str = "unknown",
        first_memory: str = "",
    ) -> TurnResult:
        """Turn 0→1: Set identity, seed vectors from first memory, force Clotho birth scene."""
        logger.info(f"Initializing session — player='{player_id}', name='{name}', memory='{first_memory[:40]}'")

        # A new thread starts clean regardless of what this kernel held
        # before — initialize() must not inherit a prior life's state.
        self.state = ThreadState()
        self._cancel_morpheus()
        self._beat_sheet = None
        self._cancel_scribe()
        self._chapters = []
        self._thread_id = None

        # Validate hamartia ("Unformed" is allowed — Lachesis overwrites at Turn 10)
        if hamartia != "Unformed" and hamartia not in settings.hamartia_options:
            logger.warning(f"Invalid hamartia '{hamartia}', defaulting to first option.")
            hamartia = settings.hamartia_options[0]

        # Set up state
        self.state.session.player_id = player_id
        self.state.session.player_name = name
        self.state.session.player_gender = gender
        self.state.session.first_memory = first_memory
        self.state.soul_ledger.hamartia = hamartia
        if hamartia and hamartia != "Unformed":
            self.state.soul_ledger.hamartia_profile = get_hamartia_profile(hamartia)
            self.state.life_voice = get_life_voice(hamartia, self.state)

        # -----------------------------------------------------------
        # Seed soul vectors from first memory archetype (+2 boost)
        # -----------------------------------------------------------
        _MEMORY_VECTOR_MAP = {
            "light": "metis",    # "A light in the distance I could not reach."
            "stone": "bia",      # "The weight of a heavy stone in my hand."
            "crowd": "kleos",    # "A crowd shouting a name that was not mine."
            "shadow": "aidos",   # "A cold shadow that moved when I moved."
        }
        for keyword, vector_name in _MEMORY_VECTOR_MAP.items():
            if keyword in first_memory.lower():
                current = getattr(self.state.soul_ledger.vectors, vector_name)
                setattr(self.state.soul_ledger.vectors, vector_name, min(current + 2, 10.0))
                logger.info(f"Memory seed: {vector_name} +2 ('{keyword}' found)")
                break

        # -----------------------------------------------------------
        # DB: ensure player + compute run_number FIRST — deterministic world
        # selection is seeded by (player_id, run_number), so it must be known
        # before the world is picked.
        # -----------------------------------------------------------
        await ensure_player(player_id)
        prior_threads = await get_dead_threads(player_id)
        self.state.session.run_number = len(prior_threads) + 1

        # -----------------------------------------------------------
        # Seed the world from first memory archetype (Sprint 10 → cartridge registry)
        # -----------------------------------------------------------
        world_id, world_seed = select_world(
            first_memory,
            player_id=player_id,
            run_number=self.state.session.run_number,
        )
        self.state.world_id = world_id
        world_context = format_world_context(world_seed, name, gender)
        self.state.world_context = world_context
        self.state.canon = bootstrap_canon(world_seed, name, gender)
        _refresh_derived_environment(self.state)
        logger.info(f"World seed: {world_seed.settlement} ('{first_memory[:30]}...')")

        # DB: create thread
        self._thread_id = await create_thread(player_id, hamartia)

        ancestor = await get_last_ancestor(player_id)
        legacy_echo, legacy_delta = build_legacy_echo(ancestor)
        if legacy_echo is not None:
            self.state.legacy_echoes = [legacy_echo]
            self.state.pressures = apply_pressure_delta(self.state.pressures, legacy_delta)

        # Assayer P4 flourish: the ancestor's bound book exists DIEGETICALLY.
        # Played life → authored literature → world canon for the next life.
        ancestor_book = self._find_ancestor_book(player_id, self.state.session.run_number)
        if ancestor_book is not None:
            self.state.world_context += (
                f"\n  - A book circulates in this world: '{ancestor_book.title}'. "
                f"Few have read it; many repeat its lines wrongly. Its last page "
                f"is said to read: \"{ancestor_book.epitaph}\""
            )
            logger.info(f"Ancestor book woven into the world: {ancestor_book.book_id}")

        # Generate initial prophecy via Nemesis
        nemesis_result = await self.nemesis.generate_initial_prophecy(self.state)
        if nemesis_result.updated_prophecy:
            self.state.the_loom.current_prophecy = nemesis_result.updated_prophecy

        logger.info(f"Prophecy: '{self.state.the_loom.current_prophecy}'")

        # -----------------------------------------------------------
        # Force Turn 1: Clotho generates the actual birth scene
        # -----------------------------------------------------------
        self.state.session.turn_count = 1
        phase, age, ui_mode, beat_position, _directive = _get_turn_metadata(1)
        self.state.session.epoch_phase = phase
        self.state.session.ui_mode = ui_mode
        self.state.session.player_age = age
        self.state.session.beat_position = beat_position

        # Tag state so Clotho (mock or real) knows this is a birth scene
        self.state.last_outcome = "birth"

        # Build the birth prompt for Clotho — grounded in world seed
        birth_prompt = (
            f"This is the opening scene of a life. The player is {name}, "
            f"a {gender}, age 3.\n\n"
            f"{world_context}\n\n"
            f"The player's earliest memory is: '{first_memory}'.\n\n"
            f"Write a scene that is ALREADY IN PROGRESS. The child is in the "
            f"middle of a specific, mundane moment — a meal, a chore, watching "
            f"their parent work, playing in the dirt. Use the family members "
            f"BY NAME. Show the settlement through the child's eyes. The "
            f"'active situation' should be background pressure that the child "
            f"senses but doesn't understand.\n\n"
            f"Do NOT begin with waking up. Do NOT begin with a mystical vision. "
            f"Do NOT begin with a ceremony. Begin in the middle of ordinary life."
        )

        if legacy_echo is not None:
            birth_prompt += (
                f" An ancestor's echo haunts this world: '{legacy_echo.epitaph}'. "
                f"It leaves the mark '{legacy_echo.inherited_mark}'."
            )
            logger.info(
                f"Ancestral echo from previous thread "
                f"(hamartia: {legacy_echo.hamartia}, mark: {legacy_echo.inherited_mark})"
            )

        # Clotho generates the opening scene
        clotho_result = await self.clotho.evaluate(
            self.state,
            action=birth_prompt,
            epoch_phase=phase,
        )

        # Seed prose history with the birth scene
        self.state.prose_history.append(clotho_result.prose)

        # Persist Turn 1 to DB
        await create_turn(
            thread_id=self._thread_id,
            turn_number=1,
            action=birth_prompt,
            outcome="birth",
            prose_summary=clotho_result.prose[:200],
            soul_vectors=self.state.soul_ledger.vectors.model_dump(),
        )

        return TurnResult(
            prose=clotho_result.prose,
            state=self.state,
            turn_number=1,
            ui_choices=clotho_result.ui_choices,
        )

    # ------------------------------------------------------------------
    # Shared Pipeline: _resolve_turn (Steps 1-8)
    # ------------------------------------------------------------------

    async def _resolve_turn(self, action: str) -> TurnContext:
        """Steps 1-8: Pure game math. Shared by sync and streaming pipelines.

        Lachesis → delta application → hamartia fork → oath processing →
        parallel agent dispatch → conflict resolution → vector penalties →
        prophecy update → terminal check.

        Returns a TurnContext with everything Clotho needs, or a terminal
        context if the player has died.

        NOTE: ``self.state`` is not mutated this turn beyond session
        metadata (rolled back on rejection); all material changes happen
        on Lachesis's working copy and commit in ``_finalize_turn``. That
        invariant is what lets us use ``self.state`` directly as the
        pressure baseline instead of paying a full deepcopy per turn.
        """
        # Morpheus P2: harvest a finished re-outline before the turn moves —
        # the one sanctioned pre-turn mutation (ledger updates) happens here,
        # before any baseline reads.
        self._harvest_morpheus()
        # Scribe P3: shelve a finished chapter (no state mutation at all).
        self._harvest_scribe()

        session = self.state.session
        # Snapshot epoch metadata so a rejected action can roll back cleanly.
        prior_meta = (
            session.epoch_phase, session.ui_mode,
            session.player_age, session.beat_position,
        )
        session.turn_count += 1
        turn = session.turn_count
        # The Vigil: a self-destruction framing is redacted from every durable
        # store (log/DB/RAG). The fiction's math still reads the real action.
        crisis_flagged = flags_sensitive_input(action)
        logger.info(f"Turn {turn}: '{REDACTION_TOKEN if crisis_flagged else action}'")

        # Epoch state machine → Director metadata (Sprint 8)
        phase, age, ui_mode, beat_position, vignette_directive = _get_turn_metadata(turn)
        if phase == 4:
            # Adulthood has no authored script — the Adult Director composes
            # a beat from live state (doom, clocks, oaths, pressures, flaw).
            beat_position, vignette_directive = select_adult_beat(self.state, turn)

        # Morpheus P2: the authored beat is the ceiling over the procedural
        # floor — same slot, validated at this exact moment, silent fallback.
        pays_promise_ids: list[str] = []
        authored, pays_promise_ids = self._authored_directive(turn, beat_position)
        if authored:
            vignette_directive = authored
            logger.info(f"Authored beat plays at turn {turn} [{beat_position}]")

        session.epoch_phase = phase
        session.ui_mode = ui_mode
        session.player_age = age
        session.beat_position = beat_position
        logger.info(f"Epoch: phase={phase}, age={age}, beat={beat_position}")

        # Step 1: Lachesis evaluates state + action validity
        lachesis_result = await self.lachesis.evaluate(self.state, action)

        if not lachesis_result.valid_action:
            logger.info(f"Lachesis BLOCKED: {lachesis_result.reason}")
            # Roll back the turn entirely: count AND epoch metadata,
            # so a rejected action at an epoch boundary doesn't leave
            # the public state advertising the wrong age/UI mode.
            session.turn_count -= 1
            (session.epoch_phase, session.ui_mode,
             session.player_age, session.beat_position) = prior_meta
            invalid_trace = DeliberationTrace(
                turn_number=max(turn - 1, 1),
                proposals=[lachesis_result.proposal] if lachesis_result.proposal else [],
                winner_order=["lachesis"],
                final_reason="Lachesis rejected the action as invalid.",
            )
            # Return a "rejected" context — callers handle the rejection
            return TurnContext(
                turn=turn,
                phase=phase,
                ui_mode=ui_mode,
                action=action,
                outcome=ResolvedOutcome(
                    state=self.state,
                    action_valid=False,
                    invalid_reason=lachesis_result.reason,
                ),
                working_state=self.state,
                lachesis_result=lachesis_result,
                stratified_context="",
                nemesis_desc="",
                eris_desc="",
                player_age=age,
                beat_position=beat_position,
                vignette_directive=vignette_directive,
                scene_outcome=SceneOutcome(
                    material_changes=[lachesis_result.reason] if lachesis_result.reason else [],
                    present_npcs=[],
                    immediate_problem=self.state.session.current_environment,
                    intervening_fates=["lachesis"],
                    must_not_contradict=["Invalid actions do not occur."],
                    pressure_summary=pressure_summary(self.state),
                ),
                deliberation_trace=invalid_trace,
                pressure_summary=pressure_summary(self.state),
                crisis_flagged=crisis_flagged,
            )

        # Step 2: Apply vector deltas from Lachesis
        working_state = lachesis_result.updated_state or copy.deepcopy(self.state)
        _refresh_derived_environment(working_state)
        if lachesis_result.vector_deltas:
            working_state.soul_ledger.vectors = SoulVectorEngine.apply_deltas(
                working_state.soul_ledger.vectors,
                lachesis_result.vector_deltas,
            )
            logger.info(f"Vectors after deltas: {SoulVectorEngine.vector_summary(working_state.soul_ledger.vectors)}")

        # Step 2b: Hamartia fork (Turn 10 overwrite)
        # LLM suggestion takes priority; deterministic engine is the fallback.
        assigned_hamartia = (
            lachesis_result.assigned_hamartia
            or determine_hamartia(working_state)
        )
        if assigned_hamartia:
            working_state.soul_ledger.hamartia = assigned_hamartia
            working_state.soul_ledger.hamartia_profile = get_hamartia_profile(assigned_hamartia)
            # Scribe P3: the Fork is where the life finds its voice.
            working_state.life_voice = get_life_voice(assigned_hamartia, working_state)
            logger.info(f"HAMARTIA FORKED: 'Unformed' → '{assigned_hamartia}'")
            logger.info(f"Life-voice: {working_state.life_voice[:60]}...")
        elif (
            working_state.soul_ledger.hamartia
            and working_state.soul_ledger.hamartia != "Unformed"
            and working_state.soul_ledger.hamartia_profile is None
        ):
            working_state.soul_ledger.hamartia_profile = get_hamartia_profile(
                working_state.soul_ledger.hamartia
            )

        # Step 2c: Doom progression — an existing doom advances (or lifts,
        # if escapable and its cause was answered) before this turn's
        # events can seal a new one. Escape reads last turn's pressures:
        # "did you answer the cause by the start of this turn?"
        doom_note = advance_doom(working_state)
        if doom_note:
            logger.info(f"Doom: {doom_note}")

        # Step 2d: The Promise Ledger keeps its books. An authored beat that
        # plays pays its promises; promises past their window are abandoned
        # (fate notices unpaid debts — omen tooth applied in step 8).
        if pays_promise_ids:
            for note in mark_paid(working_state, pays_promise_ids, turn):
                logger.info(f"Ledger: {note}")
        abandonment_notes = audit_ledger(working_state, turn)

        # Step 3: Process oaths (detect -> parse -> verify)
        oath_broken_id: str | None = None
        broken_ids, fulfilled_ids, transformed_ids = verify_oaths(working_state, action)
        # Authority inversion: Lachesis's oath_violation is an unverified model
        # string. Honor it only if it names an actually-active oath — the LLM may
        # point at a real oath, never invent one to seal an inescapable death.
        if is_verifiable_violation(
            lachesis_result.oath_violation or "",
            working_state.soul_ledger.active_oaths,
        ):
            broken_ids.append(lachesis_result.oath_violation)

        seen_ids: set[str] = set()
        broken_ids = [oath_id for oath_id in broken_ids if not (oath_id in seen_ids or seen_ids.add(oath_id))]
        if broken_ids:
            oath_broken_id = broken_ids[0]
            # A broken oath no longer kills on the spot — it seals an
            # inescapable doom. Death arrives two turns later, staged.
            broken_oath = next(
                (o for o in working_state.soul_ledger.active_oaths
                 if o.oath_id == oath_broken_id),
                None,
            )
            begin_doom(
                working_state,
                cause="broken_oath",
                description=(
                    f"An oath was broken: '{broken_oath.text}'. "
                    "Nemesis has claimed the debt; the thread is already cut, "
                    "it just hasn't finished falling."
                    if broken_oath else
                    "A sworn oath was broken. Nemesis has claimed the debt."
                ),
                max_stage=3,
                escapable=False,
            )

        for oath in working_state.soul_ledger.active_oaths:
            if oath.oath_id in broken_ids:
                oath.broken = True
                oath.status = "broken"
                oath.fulfillment_note = f"Broken on turn {turn}."
                logger.info(f"Oath BROKEN: {oath.text}")
            elif oath.oath_id in fulfilled_ids and oath.status == "active":
                oath.status = "fulfilled"
                oath.fulfillment_note = f"Fulfilled on turn {turn}."
                logger.info(f"Oath FULFILLED: {oath.text}")
            elif oath.oath_id in transformed_ids and oath.status == "active":
                oath.status = "transformed"
                oath.fulfillment_note = f"Transformed on turn {turn}."
                logger.info(f"Oath TRANSFORMED: {oath.text}")

        oath_text = lachesis_result.oath_detected or detect_oath(action)
        if oath_text and not any(
            oath.text.lower() == oath_text.lower() and oath.status == "active"
            for oath in working_state.soul_ledger.active_oaths
        ):
            new_oath = Oath(
                oath_id=f"oath_{uuid.uuid4().hex[:8]}",
                text=oath_text,
                turn_sworn=turn,
                terms=parse_oath_text(
                    oath_text,
                    subject=working_state.session.player_name or "I",
                ),
            )
            working_state.soul_ledger.active_oaths.append(new_oath)
            logger.info(f"New oath sworn: '{new_oath.text}'")

        if lachesis_result.environment_update:
            apply_environment_update(working_state, lachesis_result.environment_update)
        else:
            _refresh_derived_environment(working_state)

        # Step 4: Parallel agent evaluation
        atropos_result, nemesis_result, eris_result = await asyncio.gather(
            self.atropos.evaluate(
                working_state, action,
                nemesis_lethal=(oath_broken_id is not None),
            ),
            self.nemesis.evaluate(
                working_state, action,
                oath_broken=oath_broken_id,
            ),
            self.eris.evaluate(working_state, action),
        )

        logger.info(
            f"Agents: atropos={atropos_result.terminal_state}, "
            f"nemesis={nemesis_result.intervene}({nemesis_result.intervention_type}), "
            f"eris={eris_result.chaos_triggered}"
        )

        # Step 5: Conflict Resolution
        outcome = self.resolver.resolve(
            state=working_state,
            lachesis=lachesis_result,
            atropos=atropos_result,
            nemesis=nemesis_result,
            eris=eris_result,
        )

        # Step 6: Apply Eris vector_chaos if triggered
        if outcome.eris_struck and outcome.vector_chaos:
            outcome.state.soul_ledger.vectors = SoulVectorEngine.apply_deltas(
                outcome.state.soul_ledger.vectors,
                outcome.vector_chaos,
            )
            logger.info(f"Eris chaos applied: {outcome.vector_chaos}")

        # Step 7: Apply Nemesis vector_penalty if triggered
        if outcome.nemesis_struck and outcome.vector_penalty:
            outcome.state.soul_ledger.vectors = SoulVectorEngine.apply_deltas(
                outcome.state.soul_ledger.vectors,
                outcome.vector_penalty,
            )
            logger.info(f"Nemesis penalty applied: {outcome.vector_penalty}")

        # Step 8: Store prophecy if updated
        if outcome.prophecy_updated:
            outcome.state.the_loom.current_prophecy = outcome.prophecy_updated
            logger.info(f"Prophecy updated: '{outcome.prophecy_updated}'")

        # self.state is the untouched pre-turn baseline (see method note),
        # so it serves directly — no per-turn deepcopy.
        pressure_evolution = evolve_pressures(
            self.state,
            action,
            outcome,
            proposal_pressure=outcome.pressure_delta,
        )
        outcome.state.pressures = apply_pressure_delta(
            self.state.pressures,
            pressure_evolution.delta,
            stable_turn=pressure_evolution.stable_turn,
        )
        if outcome.scene_outcome is not None:
            outcome.scene_outcome.pressure_changes = pressure_evolution.delta
            outcome.scene_outcome.pressure_summary = pressure_evolution.summary
        outcome.state.last_action = action

        # Step 8a2: The omen tooth — a promise the story failed to pay is a
        # debt fate collects interest on. Abandonments noted for Clotho too.
        if abandonment_notes:
            outcome.state.pressures = apply_pressure_delta(
                outcome.state.pressures,
                {"omen": round(ABANDONMENT_OMEN * len(abandonment_notes), 2)},
            )
            if outcome.scene_outcome is not None:
                outcome.scene_outcome.material_changes.extend(abandonment_notes[:2])

        # Step 8b: Runaway pressures can seal an escapable doom
        # (mortal wounds, a manhunt) now that this turn's pressure landed.
        pressure_doom_note = maybe_begin_pressure_dooms(outcome.state)
        if pressure_doom_note and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.append(pressure_doom_note)

        # Step 8b': the slow doom of age — a long, UNDOOMED thread finally bends
        # toward a natural close (OLD-C3 seam: after the pressure dooms, BEFORE the
        # step-8c clock tick; begun at stage 1, first seen by Atropos next turn).
        old_age_note = maybe_begin_old_age_doom(outcome.state)
        if old_age_note and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.append(old_age_note)

        # Step 8c (agency, BEFORE the tick): shielding a claiming clock's named
        # target buys them time — a protective turn can net the claim back toward
        # zero before it advances (The World Takes, NC-5d).
        relief_notes = relieve_clock(outcome.state, action)
        if relief_notes and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.extend(relief_notes[:2])

        # Step 8c: Scene clocks tick — the world's problems mature whether
        # or not the player attends them. Fired clocks become true.
        tick = tick_scene_clocks(
            outcome.state,
            intervention_struck=(outcome.nemesis_struck or outcome.eris_struck),
            resolution_beat=(beat_position == "RESOLUTION"),
        )
        if tick.pressure_spike:
            outcome.state.pressures = apply_pressure_delta(
                outcome.state.pressures, tick.pressure_spike
            )
        for fired_clock in tick.fired:
            logger.info(f"CLOCK FIRED: {fired_clock.label} — {fired_clock.stakes}")
            # WB-C1/C2: a lethal clock dooms only in adulthood, only via the
            # staged doom (never an instant sever). The clock still fires either
            # way — its stakes become scene truth above.
            _doom_from_lethal_clock(outcome.state, fired_clock)
        if tick.notes and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.extend(tick.notes)
            outcome.scene_outcome.must_not_contradict.append(
                "A clock has run out: its stakes are now true and cannot be walked back."
            )
        # The World Takes: a clock claimed a named NPC this turn. They are dead in
        # canon (status -> "dead", already dropped from the present cast and guarded
        # by Momus), and the prose may not soften it (NC-3).
        if tick.claimed and outcome.scene_outcome is not None:
            for name in tick.claimed:
                outcome.scene_outcome.must_not_contradict.append(
                    f"{name} died this turn — they cannot appear unharmed, relieved, or safe."
                )

        # Step 8d: the present cast remembers what the player did to them —
        # deterministic, friction-weighted, read-only to Clotho (Depth). Runs on
        # outcome.state (commits in _finalize_turn); the invalid path returned
        # before step-8, so only committed actions reach here.
        rel_notes = update_npc_relations(outcome.state, action, outcome)
        if rel_notes and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.extend(rel_notes[:2])

        # Step 8d': the witnesses can LEAVE — a present NPC betrayed past returning
        # departs the scene for good (status -> "departed"), still remembered but
        # gone from the cast. Deterministic; runs after the betrayal just landed.
        depart_notes = maybe_depart_npcs(outcome.state)
        if depart_notes and outcome.scene_outcome is not None:
            outcome.scene_outcome.material_changes.extend(depart_notes[:2])

        # Step 8d'': the witnesses can ARRIVE — a latent NPC enters when its
        # earned condition is met. Last in the lifecycle block so it reads the
        # turn's fully settled cast. Suppressed on a LOSS turn (a fresh grave or a
        # slammed door is never stepped over by a newcomer in the same beat,
        # ARR-C6); an active doom suppresses it inside the function (ARR-C5).
        loss_turn = bool(tick.claimed) or bool(depart_notes)
        if not loss_turn:
            arrival = maybe_arrive_npcs(outcome.state)
            if arrival.arrived_id and outcome.scene_outcome is not None:
                outcome.scene_outcome.material_changes.extend(arrival.notes[:1])
                arrived = outcome.state.canon.npcs[arrival.arrived_id]
                outcome.scene_outcome.must_not_contradict.append(
                    f"{arrived.name} has just arrived and is present in the scene; "
                    "they may appear and act."
                )

        _refresh_derived_environment(outcome.state)

        # Set last_outcome for Clotho's context
        if outcome.nemesis_struck:
            outcome.state.last_outcome = "nemesis"
        elif outcome.eris_struck:
            outcome.state.last_outcome = "eris"
        elif fulfilled_ids:
            outcome.state.last_outcome = "oath_fulfilled"
        elif transformed_ids:
            outcome.state.last_outcome = "oath_transformed"

        # Build stratified context (Chronicle + Short-Term + Soul Mirror)
        stratified = _build_stratified_context(outcome.state)

        # Terminal check
        terminal = outcome.terminal
        death_reason = outcome.death_reason if terminal else ""

        return TurnContext(
            turn=turn,
            phase=phase,
            ui_mode=ui_mode,
            action=action,
            outcome=outcome,
            working_state=working_state,
            lachesis_result=lachesis_result,
            stratified_context=stratified,
            nemesis_desc=outcome.nemesis_description,
            eris_desc=outcome.eris_description,
            terminal=terminal,
            death_reason=death_reason,
            player_age=age,
            beat_position=beat_position,
            vignette_directive=vignette_directive,
            scene_outcome=outcome.scene_outcome,
            deliberation_trace=outcome.deliberation_trace,
            pressure_summary=pressure_evolution.summary,
            atropos_warning=(
                "" if atropos_result.terminal_state
                else atropos_result.death_reason
            ),
            crisis_flagged=crisis_flagged,
        )

    # ------------------------------------------------------------------
    # Shared Pipeline: Clotho pass + Momus repair
    # ------------------------------------------------------------------

    async def _request_clotho_pass(
        self,
        ctx: TurnContext,
        action: str,
        *,
        repair_brief: str = "",
    ) -> tuple[str, list[str]]:
        """Request one non-streaming Clotho pass and parse it."""
        clotho_result = await self.clotho.evaluate(
            ctx.outcome.state,
            action,
            nemesis_desc=ctx.nemesis_desc,
            eris_desc=ctx.eris_desc,
            epoch_phase=ctx.phase,
            stratified_context=ctx.stratified_context,
            vignette_directive=ctx.vignette_directive,
            scene_outcome=ctx.scene_outcome,
            repair_brief=repair_brief,
            fate_warning=ctx.atropos_warning,
        )
        prose, choices = _parse_clotho_output(clotho_result.prose, ctx.phase)
        return self._append_interventions(prose, ctx), choices

    async def _repair_prose_if_needed(
        self,
        ctx: TurnContext,
        action: str,
        prose: str,
        choices: list[str],
    ) -> tuple[str, list[str], MomusValidation, bool]:
        """Validate prose and retry Clotho once if Momus demands repair.

        Severity gate: a single minor hallucination commits Momus's
        deterministically corrected prose directly — a full Clotho retry
        (the most expensive call in the pipeline, doubled) is reserved
        for drift bad enough to warrant it.
        """
        validation = await self.momus.validate_prose(prose, ctx.outcome.state)
        if not validation.repair_needed:
            return prose, choices, validation, False

        logger.warning(f"Momus hallucinations: {validation.hallucinations}")

        minor_drift = (
            len(validation.hallucinations) < settings.momus_retry_min_issues
            and bool(validation.corrected_prose.strip())
        )
        if minor_drift:
            logger.info(
                "Momus: minor drift — committing corrected prose without a Clotho retry."
            )
            return validation.corrected_prose, choices, validation, True

        retry_prose, retry_choices = await self._request_clotho_pass(
            ctx, action, repair_brief=validation.repair_brief
        )
        retry_validation = await self.momus.validate_prose(
            retry_prose, ctx.outcome.state
        )

        if retry_validation.repair_needed:
            safe_prose = (
                retry_validation.corrected_prose
                or validation.corrected_prose
                or prose
            )
            logger.warning(
                "Momus repair retry still drifted; committing safer fallback. "
                f"Issues: {retry_validation.hallucinations}"
            )
            return (
                safe_prose,
                retry_choices or choices,
                retry_validation.model_copy(update={"corrected_prose": safe_prose}),
                True,
            )

        return retry_prose, retry_choices or choices, retry_validation, True

    # ------------------------------------------------------------------
    # Shared Pipeline: Sophia — the semantic judge tier (after Momus)
    # ------------------------------------------------------------------

    async def _judge_prose_if_needed(
        self,
        ctx: TurnContext,
        action: str,
        prose: str,
        choices: list[str],
    ) -> tuple[str, list[str], list[str], MomusValidation | None]:
        """Sophia's semantic pass after Momus's factual gate.

        Refuse-only (ADJ-E3): pass-as-is → else ONE targeted critique-brief
        regenerate → if it now passes commit it, else commit the ORIGINAL
        Momus-cleared draft and park the unresolved brief for next turn.
        Never selects a draft by score; Sophia writes no state.

        Returns (prose, choices, sophia_residue, validation_override). The
        override is the REGENERATION's Momus validation when a regen replaces the
        prose, so _finalize_turn corrects/commits the regen rather than reverting
        to the stale base-draft validation; it is None when the prose is left
        unchanged (the caller keeps the base draft's validation).
        """
        critique = await self.sophia.judge(prose, ctx)
        if critique.verdict != "revise" or not critique.judged:
            return prose, choices, [], None

        revisions = 0
        while revisions < settings.sophia_max_revisions:
            revisions += 1
            regen_prose, regen_choices = await self._request_clotho_pass(
                ctx, action, repair_brief=critique.critique_brief
            )
            # Re-police the regeneration: Momus (factual) then Sophia (semantic).
            regen_prose, regen_choices, regen_validation, _ = await self._repair_prose_if_needed(
                ctx, action, regen_prose, regen_choices
            )
            regen_critique = await self.sophia.judge(regen_prose, ctx)
            if regen_critique.verdict != "revise" or not regen_critique.judged:
                # The regen is committed — hand back ITS validation so the
                # finalizer operates on the prose actually being finalized, not
                # the base draft Sophia just rejected.
                return regen_prose, regen_choices or choices, [], regen_validation
            critique = regen_critique

        residue = [critique.critique_brief] if critique.critique_brief else []
        logger.info("Sophia: unresolved after revision — keeping original, deferring brief.")
        return prose, choices, residue, None

    async def _grade_and_defer(self, ctx: TurnContext, prose: str) -> list[str]:
        """Stream path: GRADE the already-streamed prose, never regenerate it.

        The player has already read the tokens; a post-stream swap is
        forbidden (ADJ-E4). An unresolved critique only parks its brief for
        next turn's craft notes.
        """
        critique = await self.sophia.judge(prose, ctx)
        if critique.verdict == "revise" and critique.judged and critique.critique_brief:
            return [critique.critique_brief]
        return []

    # ------------------------------------------------------------------
    # Shared Pipeline: _finalize_turn (Step 10+)
    # ------------------------------------------------------------------

    async def _finalize_turn(
        self,
        ctx: TurnContext,
        prose: str,
        choices: list[str],
        validation: MomusValidation | None = None,
        sophia_residue: list[str] | None = None,
    ) -> TurnResult:
        """Step 10+: Post-prose bookkeeping. Shared by sync and streaming.

        Momus validation → milestone check → prose history append →
        Chronicler compression → RAG indexing → state commit → DB persist.
        """
        outcome = ctx.outcome

        # Momus validation
        if validation is None:
            validation = await self.momus.validate_prose(prose, outcome.state)
        if validation.hallucinations:
            logger.warning(f"Momus hallucinations: {validation.hallucinations}")
        if validation.repair_needed:
            prose = validation.corrected_prose or prose
        if validation.law_violations:
            logger.warning(f"Momus law violations: {validation.law_violations}")
        # Law violations + unresolved Sophia critique briefs become next turn's
        # craft notes — Momus's criticism and the judge's residue feed Clotho's
        # next scene instead of dying in the log. The single, capped writer of
        # craft_notes (ADJ-E5): merge, dedupe, slice — never clobber, never grow.
        residue = sophia_residue or []
        merged = list(dict.fromkeys(list(validation.law_violations) + list(residue)))
        outcome.state.craft_notes = merged[: settings.craft_notes_max]

        # Milestone check (any vector == 10)
        is_milestone, milestone_vec = SoulVectorEngine.is_milestone(
            outcome.state.soul_ledger.vectors
        )
        image_url = ""
        if is_milestone:
            outcome.state.the_loom.milestone_reached = True
            outcome.state.the_loom.image_prompt_trigger = (
                f"A mortal's {milestone_vec} reaches its zenith. "
                f"Environment: {outcome.state.session.current_environment}"
            )
            logger.info(f"MILESTONE: {milestone_vec} reached 10!")
        else:
            outcome.state.the_loom.milestone_reached = False
            outcome.state.the_loom.image_prompt_trigger = ""

        # Prose history + Chronicler compression
        outcome.state.prose_history.append(prose)

        if (ctx.turn % settings.chronicle_interval == 0
                and len(outcome.state.prose_history) >= settings.chronicle_interval):
            window = outcome.state.prose_history[-settings.chronicle_interval:]
            logger.info(f"Chronicler triggered at turn {ctx.turn} — compressing {len(window)} turns")
            chronicle_result = await self.chronicler.evaluate(
                outcome.state, ctx.action, prose_window=window,
            )
            # Mythic track
            if chronicle_result.chronicle_sentence:
                outcome.state.chronicle.append(chronicle_result.chronicle_sentence)
                await append_chronicle(self._thread_id, chronicle_result.chronicle_sentence)
                logger.info(f"Chronicle [{len(outcome.state.chronicle)}]: {chronicle_result.chronicle_sentence}")

            # Factual track
            if chronicle_result.factual_digest:
                outcome.state.factual_chronicle.append(chronicle_result.factual_digest)
                await append_factual_chronicle(self._thread_id, chronicle_result.factual_digest)
                logger.info(f"Factual [{len(outcome.state.factual_chronicle)}]: {chronicle_result.factual_digest}")

            # Flush the prose history buffer
            _retain = settings.chronicle_prose_retention
            outcome.state.prose_history = outcome.state.prose_history[-_retain:]

        # Cap prose_history to prevent unbounded growth between compressions
        _cap = settings.chronicle_interval + settings.chronicle_prose_retention
        if len(outcome.state.prose_history) > _cap:
            outcome.state.prose_history = outcome.state.prose_history[-_cap:]

        # RAG indexing + retrieval run concurrently (both are to_thread
        # wrapped ChromaDB calls); the query intentionally retrieves PAST
        # turns as context, so it does not need to see this turn's add.
        add_result, query_result = await asyncio.gather(
            self.rag.add_turn(
                turn_number=ctx.turn,
                action=_persisted_action(ctx),
                outcome=outcome.state.last_outcome or "neutral",
                prose_summary=prose[:200],
                environment=outcome.state.session.current_environment,
            ),
            self.rag.query(ctx.action, n_results=5),
            return_exceptions=True,
        )
        if isinstance(add_result, BaseException):
            logger.warning(f"RAG indexing failed: {add_result}")
        if isinstance(query_result, BaseException):
            logger.warning(f"RAG query failed: {query_result}")
        else:
            outcome.state.rag_context = query_result

        # Commit state
        self.state = outcome.state
        _refresh_derived_environment(self.state)

        # Clear consumed dream (it was already fed to Clotho via stratified context)
        self.state.current_dream = ""

        logger.info(
            f"Turn {ctx.turn} complete. "
            f"Vectors: {SoulVectorEngine.vector_summary(self.state.soul_ledger.vectors)}, "
            f"Imbalance: {SoulVectorEngine.imbalance_score(self.state.soul_ledger.vectors):.1f}"
        )

        # DB persist
        await create_turn(
            thread_id=self._thread_id,
            turn_number=ctx.turn,
            action=_persisted_action(ctx),
            outcome=outcome.state.last_outcome or "neutral",
            prose_summary=prose[:200],
            soul_vectors=outcome.state.soul_ledger.vectors.model_dump(),
        )

        return TurnResult(
            prose=prose,
            state=self.state,
            terminal=False,
            nemesis_struck=outcome.nemesis_struck,
            eris_struck=outcome.eris_struck,
            turn_number=ctx.turn,
            image_url=image_url,
            ui_choices=choices,
        )

    # ------------------------------------------------------------------
    # Shared Pipeline: _handle_death (terminal path)
    # ------------------------------------------------------------------

    async def _handle_death(self, ctx: TurnContext) -> TurnResult:
        """Terminal path: epitaph + the Bookbinder's hour + DB + death result."""
        self._cancel_morpheus()  # the Author has no future to write here
        self._beat_sheet = None
        self.state = ctx.outcome.state
        # Drop the permanence latch the instant death commits. From here on, any
        # further action is refused at the turn entrypoints — no second death,
        # no re-bound book, no duplicate verdict. Death is the engine's to keep.
        self.state.terminal = True
        self.state.death_reason = ctx.death_reason
        _refresh_derived_environment(self.state)
        epitaph = await self._generate_epitaph(ctx.outcome.state, ctx.turn, ctx.death_reason)

        # Scribe P3: the life becomes a book. Failure costs the book, never
        # the death — book_id is "" and the thread still joins the Tapestry.
        book_id = await self._bind_book_at_death(epitaph, ctx.death_reason)

        # Assayer P4: the life becomes a measurement. Same constitution:
        # a verdict failure costs the verdict, never the death.
        try:
            verdict = compute_verdict(
                self.state, death_reason=ctx.death_reason, book_id=book_id
            )
            write_verdict(verdict)
        except Exception as exc:
            logger.error(f"Assay failed: {exc!r} — the death stands, unweighed.")

        # DB persist
        await create_turn(
            thread_id=self._thread_id,
            turn_number=ctx.turn,
            action=_persisted_action(ctx),
            outcome="terminal",
            prose_summary=ctx.death_reason[:200],
            soul_vectors=ctx.outcome.state.soul_ledger.vectors.model_dump(),
        )

        return TurnResult(
            prose=f"**THREAD SEVERED**\n\n{ctx.death_reason}",
            state=ctx.outcome.state,
            terminal=True,
            death_reason=ctx.death_reason,
            turn_number=ctx.turn,
            book_id=book_id,
            epitaph=epitaph,
        )

    # ------------------------------------------------------------------
    # Shared: Dream prefetch (epoch boundaries)
    # ------------------------------------------------------------------

    def _maybe_start_dream_task(self, ctx: TurnContext) -> asyncio.Task | None:
        """Start Hypnos weaving concurrently with prose generation.

        Dreams fire on childhood RESOLUTION beats. Starting the task here
        (instead of awaiting after finalize) hides the entire Haiku call
        behind Clotho's much longer generation.
        """
        if ctx.terminal or ctx.beat_position != "RESOLUTION" or ctx.phase > 3:
            return None
        return asyncio.create_task(self.hypnos.weave_dream(ctx.outcome.state))

    @staticmethod
    async def _settle_dream_task(dream_task: asyncio.Task | None) -> str:
        """Await a prefetched dream, tolerating failure."""
        if dream_task is None:
            return ""
        try:
            return await dream_task
        except Exception as e:
            logger.warning(f"Hypnos dream prefetch failed: {e}")
            return ""

    @staticmethod
    def _cancel_dream_task(dream_task: asyncio.Task | None) -> None:
        """Cancel an unconsumed dream task (client disconnect path)."""
        if dream_task is not None and not dream_task.done():
            dream_task.cancel()

    # ------------------------------------------------------------------
    # Morpheus P2: fire / harvest / consume (the Re-Outliner lifecycle)
    # ------------------------------------------------------------------

    def _build_morpheus_snapshot(self) -> MorpheusSnapshot:
        """Freeze the lived epoch for the Re-Outliner.

        Built from committed state AFTER finalize at a RESOLUTION turn —
        Morpheus reads the photograph, never the room. Floor beats for
        the next three turns ride along as the procedural base to elevate.
        """
        state = self.state
        boundary = state.session.turn_count
        floors: list[FloorBeat] = []
        for turn in range(boundary + 1, boundary + 4):
            phase, _age, _ui, position, directive = _get_turn_metadata(turn)
            if phase == 4:
                position, directive = select_adult_beat(state, turn)
            floors.append(FloorBeat(turn=turn, position=position, directive=directive))

        vectors = state.soul_ledger.vectors
        clock_lines: list[str] = []
        npc_names: list[str] = []
        if state.canon:
            npc_names = [
                npc.name for npc in state.canon.npcs.values() if npc.status == "alive"
            ]
            clock_lines = [
                f"{c.clock_id}|{c.label}|{c.progress}/{c.max_segments}"
                for c in state.canon.clocks.values()
            ]

        return MorpheusSnapshot(
            thread_stamp=f"{state.session.player_id}:{state.session.run_number}",
            boundary_turn=boundary,
            epoch_start_turn=boundary + 1,
            prose_window=list(state.prose_history[-4:]),
            factual_chronicle=list(state.factual_chronicle),
            chronicle=list(state.chronicle),
            last_action=state.last_action,
            soul_summary=(
                f"{SoulVectorEngine.vector_summary(vectors)} — "
                f"hamartia {state.soul_ledger.hamartia or 'Unformed'}"
            ),
            pressure_summary=pressure_summary(state),
            npc_names_alive=npc_names,
            clock_lines=clock_lines,
            active_promises=[p.model_copy(deep=True) for p in active_promises(state)],
            floor_beats=floors,
        )

    def _maybe_start_morpheus(self, ctx: TurnContext) -> None:
        """Fire the Re-Outliner behind the dream-curtain at epoch boundaries."""
        if ctx.terminal or ctx.beat_position != "RESOLUTION":
            return
        self._cancel_morpheus()  # newest boundary wins
        snapshot = self._build_morpheus_snapshot()
        self._morpheus_task = asyncio.create_task(self.morpheus.reoutline(snapshot))
        logger.info(f"Morpheus fired for epoch starting turn {snapshot.epoch_start_turn}")

    def _harvest_morpheus(self) -> None:
        """Collect a finished re-outline, gate it, apply its ledger updates.

        Called at the top of each turn, BEFORE the turn counter moves and
        before any baseline reads — the one sanctioned pre-turn mutation
        (the ledger), documented against _resolve_turn's invariant.
        A failed/invalid/stale sheet costs nothing: the floor plays.
        """
        task = self._morpheus_task
        if task is None or not task.done():
            return
        self._morpheus_task = None

        try:
            sheet = task.result()
        except Exception as exc:
            logger.warning(f"Morpheus task failed: {exc!r} — the floor plays.")
            return
        if sheet is None:
            return

        # Validity stamps (validate-on-consume, layer 1).
        expected_stamp = f"{self.state.session.player_id}:{self.state.session.run_number}"
        next_turn = self.state.session.turn_count + 1
        if sheet.thread_stamp != expected_stamp:
            logger.warning(f"Morpheus sheet stamp mismatch ({sheet.thread_stamp}) — dropped.")
            return
        if not (sheet.epoch_start_turn <= next_turn <= sheet.epoch_start_turn + 2):
            logger.warning(
                f"Morpheus sheet window stale (serves {sheet.epoch_start_turn}.."
                f"{sheet.epoch_start_turn + 2}, next turn {next_turn}) — dropped."
            )
            return

        # The beat gate: Momus mocks the Author too. Drop failing beats.
        kept = []
        for beat in sheet.beats:
            violations = gate_beat(beat, self.state)
            if violations:
                logger.warning(
                    f"Morpheus beat [{beat.position}] failed the gate: {violations}"
                )
            else:
                kept.append(beat)
        if not kept:
            logger.warning("Morpheus: no beats survived the gate — the floor plays.")
            return

        # Ledger updates apply through the engine, constitutionally validated.
        notes = apply_ledger_updates(
            self.state, sheet.ledger_updates, based_on_turn=sheet.based_on_turn
        )
        for note in notes:
            logger.info(f"Ledger: {note}")

        self._beat_sheet = sheet.model_copy(update={"beats": kept})
        logger.info(
            f"Morpheus sheet harvested: {len(kept)} beat(s) for turns "
            f"{sheet.epoch_start_turn}..{sheet.epoch_start_turn + 2}"
        )

    def _authored_directive(self, turn: int, position: str) -> tuple[str, list[str]]:
        """The ceiling over the floor: an authored beat, if one is valid NOW.

        Returns (directive, pays_promise_ids) or ("", []). Preconditions are
        re-checked against live canon at this exact moment — a plan is a
        suggestion; canon is the truth. Staleness costs one beat.
        """
        sheet = self._beat_sheet
        if sheet is None:
            return "", []
        if not (sheet.epoch_start_turn <= turn <= sheet.epoch_start_turn + 2):
            return "", []
        beat = sheet.beat_for(position)
        if beat is None:
            return "", []
        if not preconditions_hold(beat, self.state):
            logger.info(
                f"Authored beat [{position}] preconditions failed at consumption — floor plays."
            )
            return "", []
        return beat.directive, list(beat.pays_promise_ids)

    def _cancel_morpheus(self) -> None:
        if self._morpheus_task is not None and not self._morpheus_task.done():
            self._morpheus_task.cancel()
        self._morpheus_task = None

    # ------------------------------------------------------------------
    # Scribe P3: the write-behind biography
    # ------------------------------------------------------------------

    _EPOCH_NAMES: dict[int, str] = {
        1: "The Hearth",
        2: "The World Outside",
        3: "The Crucible",
    }

    def _epoch_name(self, index: int) -> str:
        return self._EPOCH_NAMES.get(index, f"The Open Road, Part {index - 3}")

    def _settlement_name(self) -> str:
        if not self.state.canon:
            return ""
        for loc in self.state.canon.locations.values():
            if "settlement" in loc.tags:
                return loc.name
        return ""

    def _build_scribe_snapshot(
        self,
        *,
        epoch_index: int,
        covers: tuple[int, int],
        death_reason: str = "",
        epitaph: str = "",
    ) -> ScribeSnapshot:
        """Freeze one lived epoch for the biographer (the photograph again)."""
        state = self.state
        npc_names: list[str] = []
        if state.canon:
            # All statuses EXCEPT latent — a biography may name its dead, but a
            # latent (authored-but-never-arrived) witness was never part of this
            # life. Feeding its name to the Scribe would leak the unsprung cast
            # into the published book, the same ARR-C14 leak client_safe_state
            # closes on the wire.
            npc_names = [
                npc.name for npc in state.canon.npcs.values() if npc.status != "latent"
            ]
        return ScribeSnapshot(
            thread_stamp=f"{state.session.player_id}:{state.session.run_number}",
            epoch_index=epoch_index,
            epoch_name=self._epoch_name(epoch_index),
            covers_turns=covers,
            boundary_turn=state.session.turn_count,
            prose_window=list(state.prose_history[-3:]),
            factual_chronicle=list(state.factual_chronicle),
            chronicle=list(state.chronicle),
            life_voice=state.life_voice,
            player_name=state.session.player_name,
            player_age=state.session.player_age,
            hamartia=state.soul_ledger.hamartia,
            settlement=self._settlement_name(),
            npc_names=npc_names,
            death_reason=death_reason,
            epitaph=epitaph,
        )

    def _maybe_start_scribe(self, ctx: TurnContext) -> None:
        """The biographer drafts the epoch just lived, behind the curtain."""
        if ctx.terminal or ctx.beat_position != "RESOLUTION":
            return
        boundary = self.state.session.turn_count
        epoch_index = boundary // 3
        if epoch_index < 1:
            return
        snapshot = self._build_scribe_snapshot(
            epoch_index=epoch_index,
            covers=(boundary - 2, boundary),
        )
        self._cancel_scribe()
        self._scribe_task = asyncio.create_task(self.scribe.draft_chapter(snapshot))
        logger.info(f"Scribe fired for chapter {epoch_index} (turns {boundary - 2}..{boundary})")

    def _harvest_scribe(self) -> None:
        """Collect a finished chapter. Failures cost a chapter, nothing more."""
        task = self._scribe_task
        if task is None or not task.done():
            return
        self._scribe_task = None
        try:
            chapter = task.result()
        except Exception as exc:
            logger.warning(f"Scribe task failed: {exc!r} — the book is shorter.")
            return
        self._accept_chapter(chapter)

    def _accept_chapter(self, chapter: Chapter | None) -> None:
        if chapter is None:
            return
        expected = f"{self.state.session.player_id}:{self.state.session.run_number}"
        if chapter.thread_stamp != expected:
            logger.warning("Scribe chapter stamp mismatch — dropped.")
            return
        if any(c.epoch_index == chapter.epoch_index for c in self._chapters):
            logger.warning(f"Duplicate chapter {chapter.epoch_index} — dropped.")
            return
        self._chapters.append(chapter)
        logger.info(f"Chapter {chapter.epoch_index} shelved: {chapter.title}")

    async def _settle_scribe_task(self) -> None:
        """At death: wait for a mid-draft chapter rather than losing it."""
        task = self._scribe_task
        self._scribe_task = None
        if task is None:
            return
        try:
            self._accept_chapter(await task)
        except Exception as exc:
            logger.warning(f"Pending chapter lost at death: {exc!r}")

    async def _bind_book_at_death(self, epitaph: str, death_reason: str) -> str:
        """The Bookbinder's hour: final chapter, assembly, publication.

        Returns the book_id, or "" if the life produced nothing bindable.
        Never raises — a failed binding costs the book, not the death.
        """
        try:
            await self._settle_scribe_task()

            covered_through = max(
                (c.covers_turns[1] for c in self._chapters), default=0
            )
            died_turn = self.state.session.turn_count
            start = min(covered_through + 1, died_turn)
            final_snapshot = self._build_scribe_snapshot(
                epoch_index=(max((c.epoch_index for c in self._chapters), default=0) + 1),
                covers=(max(start, 1), died_turn),
                death_reason=death_reason,
                epitaph=epitaph,
            )
            final_chapter = await self.scribe.draft_chapter(final_snapshot)
            self._accept_chapter(final_chapter)

            if not self._chapters:
                logger.warning("No chapters survived — this life goes unbound.")
                return ""

            manifest = bind_book(
                self.state,
                self._chapters,
                epitaph=epitaph,
                death_reason=death_reason,
            )
            write_book(manifest)
            return manifest.book_id
        except Exception as exc:
            logger.error(f"Bookbinding failed: {exc!r} — the death stands, unbound.")
            return ""
        finally:
            self._chapters = []

    def _cancel_scribe(self) -> None:
        if self._scribe_task is not None and not self._scribe_task.done():
            self._scribe_task.cancel()
        self._scribe_task = None

    @staticmethod
    def _find_ancestor_book(player_id: str, run_number: int):
        """The previous incarnation's bound life, if the shelf holds it.

        Matched by thread_stamp — never by name, which changes each life.
        Failure returns None; the flourish is optional by constitution.
        """
        if run_number < 2:
            return None
        try:
            wanted = f"{player_id}:{run_number - 1}"
            for manifest in list_books():
                if manifest.thread_stamp == wanted:
                    return manifest
        except Exception as exc:
            logger.warning(f"Ancestor-book lookup failed: {exc!r}")
        return None

    # ------------------------------------------------------------------
    # Shared: Intervention prose appending
    # ------------------------------------------------------------------

    @staticmethod
    def _append_interventions(prose: str, ctx: TurnContext) -> str:
        """Append Nemesis/Eris flavor text to Clotho's prose."""
        if ctx.outcome.nemesis_struck and ctx.nemesis_desc:
            prose += f"\n\n---\n\n*{ctx.nemesis_desc}*"
        if ctx.outcome.eris_struck and ctx.eris_desc:
            prose += f"\n\n---\n\n*{ctx.eris_desc}*"
        return prose

    # ------------------------------------------------------------------
    # Turn 1+: Sync pipeline (thin orchestration shell)
    # ------------------------------------------------------------------

    def _severed_result(self) -> TurnResult:
        """The fixed no-op a severed thread returns for any further action."""
        return TurnResult(
            prose=(
                "**THE THREAD IS SEVERED**\n\nThis life is over; what the Fates "
                "have cut cannot be rewoven."
            ),
            state=self.state,
            terminal=True,
            death_reason=self.state.death_reason,
            turn_number=self.state.session.turn_count,
        )

    async def process_turn(self, action: str) -> TurnResult:
        """Execute one full turn through the engine pipeline (sync Clotho)."""
        # Permanence: a severed thread takes no more turns. Refuse before any
        # state mutation — no turn advance, no council, no persistence.
        if self.state.terminal:
            return self._severed_result()
        ctx = await self._resolve_turn(action)

        # Rejected by Lachesis
        if not ctx.outcome.action_valid:
            return TurnResult(
                prose=f"*{ctx.outcome.invalid_reason}*\n\nThe world does not bend to impossible demands.",
                state=self.state,
                turn_number=ctx.turn,
            )

        # Death
        if ctx.terminal:
            return await self._handle_death(ctx)

        # Dream prefetch: Hypnos weaves while Clotho speaks
        dream_task = self._maybe_start_dream_task(ctx)

        try:
            # Clotho generates prose
            prose, choices = await self._request_clotho_pass(ctx, action)
            prose, choices, validation, _ = await self._repair_prose_if_needed(
                ctx, action, prose, choices
            )
            # Sophia's semantic pass: critique-brief regeneration (refuse-only).
            prose, choices, sophia_residue, judge_validation = await self._judge_prose_if_needed(
                ctx, action, prose, choices
            )
            # If Sophia regenerated the prose, finalize against the REGEN's
            # validation — otherwise _finalize_turn's repair step would overwrite
            # the Sophia-approved prose with the base draft Sophia rejected.
            if judge_validation is not None:
                validation = judge_validation
        except BaseException:
            self._cancel_dream_task(dream_task)
            raise

        result = await self._finalize_turn(
            ctx, prose, choices, validation=validation, sophia_residue=sophia_residue
        )

        # Morpheus works behind the curtain Hypnos is about to draw;
        # the Scribe writes down what the curtain just closed on.
        self._maybe_start_morpheus(ctx)
        self._maybe_start_scribe(ctx)

        # Dream trigger: fire on Resolution beats (turns 3, 6, 9)
        dream = await self._settle_dream_task(dream_task)
        if dream:
            self.state.current_dream = dream
            logger.info(f"Hypnos dream woven at turn {ctx.turn}")

        return result

    # ------------------------------------------------------------------
    # Turn 1+: Streaming pipeline (thin orchestration shell)
    # ------------------------------------------------------------------

    async def process_turn_stream(self, action: str) -> AsyncGenerator[str, None]:
        """Execute one turn as an SSE async generator.

        Yields three phases as ``data: {...}\\n\\n`` lines:
          Phase 1 (mechanic) — Lachesis math + conflict resolution, immediate
          Phase 2 (prose)    — Clotho tokens, streamed for typewriter effect
          Phase 3 (state)    — Final state, choices, cleanup

        DB persistence is guaranteed in the finally block.
        """
        # Permanence: a severed thread takes no more turns. Refuse before the
        # try-block so the finally-persist never fires — no turn is recorded.
        if self.state.terminal:
            yield "data: " + json.dumps({
                "type": "prose",
                "text": (
                    "The thread is severed. This life is over; what the Fates "
                    "have cut cannot be rewoven."
                ),
            }) + "\n\n"
            yield "data: " + json.dumps({
                "type": "state",
                "payload": client_safe_state(self.state).model_dump(),
                "ui_choices": [],
                "terminal": True,
                "death_reason": self.state.death_reason,
            }) + "\n\n"
            return

        db_saved = False
        full_prose_buffer = ""
        ctx: TurnContext | None = None
        dream_task: asyncio.Task | None = None

        try:
            ctx = await self._resolve_turn(action)

            # Invalid action — emit rejection
            if not ctx.outcome.action_valid:
                if ctx.deliberation_trace is not None:
                    yield "data: " + json.dumps({
                        "type": "deliberation",
                        "payload": ctx.deliberation_trace.model_dump(),
                    }) + "\n\n"
                yield "data: " + json.dumps({
                    "type": "prose",
                    "text": f"*{ctx.outcome.invalid_reason}*\nThe world does not bend to impossible demands.",
                }) + "\n\n"
                yield "data: " + json.dumps({
                    "type": "state",
                    "payload": client_safe_state(self.state).model_dump(),
                    "ui_choices": [],
                    "terminal": False,
                    "death_reason": "",
                }) + "\n\n"
                return

            # Emit the mechanic event
            yield "data: " + json.dumps({
                "type": "mechanic",
                "payload": {
                    "vector_deltas": _english_deltas(ctx.lachesis_result.vector_deltas),
                    "dominant": _dominant_vector_english(ctx.lachesis_result.vector_deltas),
                    "outcome": ctx.outcome.state.last_outcome or "neutral",
                    "nemesis_struck": ctx.outcome.nemesis_struck,
                    "eris_struck": ctx.outcome.eris_struck,
                    "valid": True,
                },
            }) + "\n\n"

            if ctx.deliberation_trace is not None:
                yield "data: " + json.dumps({
                    "type": "deliberation",
                    "payload": ctx.deliberation_trace.model_dump(),
                }) + "\n\n"

            # Terminal — emit death
            if ctx.terminal:
                death_result = await self._handle_death(ctx)
                yield "data: " + json.dumps({
                    "type": "prose",
                    "text": f"**THREAD SEVERED**\n\n{ctx.death_reason}",
                }) + "\n\n"
                yield "data: " + json.dumps({
                    "type": "state",
                    "payload": client_safe_state(ctx.outcome.state).model_dump(),
                    "ui_choices": [],
                    "terminal": True,
                    "death_reason": ctx.death_reason,
                    "book_id": death_result.book_id,
                    "epitaph": death_result.epitaph,
                }) + "\n\n"
                db_saved = True  # _handle_death persists to DB
                return

            # Dream prefetch: Hypnos weaves while Clotho streams
            dream_task = self._maybe_start_dream_task(ctx)

            # ── PHASE 2: THE PROSE (Clotho streaming) ────────────
            separator = "---CHOICES---"
            separator_buffer = ""
            separator_found = False

            async for token in self.clotho.astream(
                ctx.outcome.state, action,
                nemesis_desc=ctx.nemesis_desc,
                eris_desc=ctx.eris_desc,
                epoch_phase=ctx.phase,
                stratified_context=ctx.stratified_context,
                vignette_directive=ctx.vignette_directive,
                scene_outcome=ctx.scene_outcome,
                fate_warning=ctx.atropos_warning,
            ):
                full_prose_buffer += token

                if not separator_found:
                    separator_buffer += token

                    if separator in separator_buffer:
                        separator_found = True
                        pre_sep = separator_buffer.split(separator, 1)[0]
                        if pre_sep:
                            yield "data: " + json.dumps({
                                "type": "prose", "text": pre_sep,
                            }) + "\n\n"
                    elif len(separator_buffer) > len(separator) + 20:
                        safe = separator_buffer[:-(len(separator) + 10)]
                        separator_buffer = separator_buffer[-(len(separator) + 10):]
                        yield "data: " + json.dumps({
                            "type": "prose", "text": safe,
                        }) + "\n\n"

            # Flush remaining buffer if no separator was found
            if not separator_found and separator_buffer:
                yield "data: " + json.dumps({
                    "type": "prose", "text": separator_buffer,
                }) + "\n\n"

            # Parse the full buffer for choices + interventions
            prose, choices = _parse_clotho_output(full_prose_buffer, ctx.phase)
            prose = self._append_interventions(prose, ctx)
            prose, choices, validation, repaired = await self._repair_prose_if_needed(
                ctx, action, prose, choices
            )

            if repaired:
                yield "data: " + json.dumps({
                    "type": "prose_repair",
                    "text": prose,
                }) + "\n\n"

            # Sophia GRADES the streamed render but never swaps it (ADJ-E4):
            # an unresolved critique only defers its brief to next turn.
            sophia_residue = await self._grade_and_defer(ctx, prose)

            # ── PHASE 3: STATE RESOLUTION ────────────────────────
            result = await self._finalize_turn(
                ctx, prose, choices, validation=validation,
                sophia_residue=sophia_residue,
            )
            db_saved = True

            # Morpheus works behind the curtain Hypnos is about to draw;
            # the Scribe writes down what the curtain just closed on.
            self._maybe_start_morpheus(ctx)
            self._maybe_start_scribe(ctx)

            yield "data: " + json.dumps({
                "type": "state",
                "payload": client_safe_state(result.state).model_dump(),
                "ui_choices": result.ui_choices,
                "terminal": False,
                "death_reason": "",
                "nemesis_struck": result.nemesis_struck,
                "eris_struck": result.eris_struck,
                "turn_number": result.turn_number,
            }) + "\n\n"

            # ── PHASE 4: DREAM (epoch boundary only, prefetched) ──
            dream = await self._settle_dream_task(dream_task)
            if dream:
                self.state.current_dream = dream
                yield "data: " + json.dumps({
                    "type": "dream",
                    "text": dream,
                }) + "\n\n"
                logger.info(f"Hypnos dream streamed at turn {ctx.turn}")

        except asyncio.CancelledError:
            logger.warning(f"[stream] Turn cancelled by client disconnect.")
            raise

        finally:
            # Never leak an unconsumed dream task on disconnect/error
            self._cancel_dream_task(dream_task)
            # Guarantee DB persistence even on disconnect — but ONLY for a valid,
            # turn-consuming action. A rejected action rolls back turn_count and
            # returns early without db_saved; emergency-persisting it would write a
            # phantom turn at the rolled-back number (mislabeled with the prior
            # outcome), which the next valid turn then duplicates. The sync path
            # never persists a rejected action; this keeps the stream symmetric.
            if not db_saved and self._thread_id and ctx is not None and ctx.outcome.action_valid:
                try:
                    await create_turn(
                        thread_id=self._thread_id,
                        turn_number=ctx.turn,
                        action=(REDACTION_TOKEN if flags_sensitive_input(action) else action),
                        outcome=self.state.last_outcome or "partial",
                        prose_summary=full_prose_buffer[:200] if full_prose_buffer else "disconnected",
                        soul_vectors=self.state.soul_ledger.vectors.model_dump(),
                    )
                    logger.info(f"[stream] Emergency DB persist for turn {ctx.turn}")
                except Exception as e:
                    logger.error(f"[stream] Emergency DB persist failed: {e}")

    # ------------------------------------------------------------------
    # Death Hook: Epitaph Generation
    # ------------------------------------------------------------------

    async def _generate_epitaph(
        self,
        state: ThreadState,
        turn: int,
        death_reason: str,
    ) -> str:
        """Generate mythic epitaph + persist to DB. Returns the epitaph.

        MUST be awaited (not fire-and-forget) to ensure the epitaph
        is written before the player can restart and query ancestors.
        """
        model = settings.clotho_model
        epitaph = f"Here fell one cursed by {state.soul_ledger.hamartia}. The thread is severed."

        if model != "mock":
            try:
                epitaph = await llm.generate(
                    model=model,
                    system_prompt=(
                        "You are the Chronicler of the Dead. Write a single mythic epitaph "
                        "(1-2 sentences) for a fallen mortal. It should be poetic, tragic, "
                        "and reference their fatal flaw. Output ONLY the epitaph text."
                    ),
                    user_message=(
                        f"Hamartia: {state.soul_ledger.hamartia}\n"
                        f"Death turn: {turn}\n"
                        f"Last outcome: {state.last_outcome}\n"
                        f"Environment: {state.session.current_environment}\n"
                        f"Prophecy: {state.the_loom.current_prophecy}"
                    ),
                    temperature=0.7,
                    max_tokens=150,
                )
                epitaph = epitaph.strip()
            except Exception as e:
                logger.error(f"Epitaph generation failed: {e}. Using fallback.")

        logger.info(f"Epitaph: {epitaph}")
        await update_thread_death(
            self._thread_id,
            epitaph,
            turn,
            death_reason=death_reason,
            final_soul_vectors=state.soul_ledger.vectors.model_dump(),
        )
        return epitaph

    def reset(self) -> None:
        """Destroy session and reset state."""
        try:
            self.rag.destroy()
        except Exception as e:
            logger.warning(f"RAG cleanup failed: {e}")
        self.rag = NyxRAGStore()
        self.state = ThreadState()
        self._cancel_morpheus()
        self._beat_sheet = None
        self._cancel_scribe()
        self._chapters = []
        self._thread_id = None
        logger.info("Kernel reset — new thread begins.")
