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
from app.agents.nemesis import Nemesis
from app.core.config import settings
from app.core.resolver import ConflictResolver, ResolvedOutcome
from app.core.world_seeds import get_world_seed, format_world_context
from app.schemas.state import (
    DeliberationTrace,
    LachesisResponse,
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
    derive_environment_string,
    render_scene_snapshot,
)
from app.services.hamartia_engine import determine_hamartia, get_hamartia_profile
from app.services.legacy import build_legacy_echo
from app.services.oath_engine import detect_oath, verify_oaths
from app.services.oath_parser import parse_oath_text
from app.services.pressure import apply_pressure_delta, evolve_pressures, pressure_summary
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
        self.chronicler = Chronicler()

        # Systems
        self.resolver = ConflictResolver()
        self.rag = NyxRAGStore()

        # Session state (in-memory)
        self.state = ThreadState()

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
        # Seed the world from first memory archetype (Sprint 10)
        # -----------------------------------------------------------
        world_seed = get_world_seed(first_memory)
        world_context = format_world_context(world_seed, name, gender)
        self.state.world_context = world_context
        self.state.canon = bootstrap_canon(world_seed, name, gender)
        _refresh_derived_environment(self.state)
        logger.info(f"World seed: {world_seed.settlement} ('{first_memory[:30]}...')")

        # DB: ensure player + create thread
        await ensure_player(player_id)
        prior_threads = await get_dead_threads(player_id)
        self.state.session.run_number = len(prior_threads) + 1
        self._thread_id = await create_thread(player_id, hamartia)

        ancestor = await get_last_ancestor(player_id)
        legacy_echo, legacy_delta = build_legacy_echo(ancestor)
        if legacy_echo is not None:
            self.state.legacy_echoes = [legacy_echo]
            self.state.pressures = apply_pressure_delta(self.state.pressures, legacy_delta)

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
        """
        previous_state = copy.deepcopy(self.state)
        self.state.session.turn_count += 1
        turn = self.state.session.turn_count
        logger.info(f"Turn {turn}: '{action}'")

        # Epoch state machine → Director metadata (Sprint 8)
        phase, age, ui_mode, beat_position, vignette_directive = _get_turn_metadata(turn)
        self.state.session.epoch_phase = phase
        self.state.session.ui_mode = ui_mode
        self.state.session.player_age = age
        self.state.session.beat_position = beat_position
        logger.info(f"Epoch: phase={phase}, age={age}, beat={beat_position}")

        # Step 1: Lachesis evaluates state + action validity
        lachesis_result = await self.lachesis.evaluate(self.state, action)

        if not lachesis_result.valid_action:
            logger.info(f"Lachesis BLOCKED: {lachesis_result.reason}")
            self.state.session.turn_count -= 1  # Don't count invalid turns
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
            logger.info(f"HAMARTIA FORKED: 'Unformed' → '{assigned_hamartia}'")
        elif (
            working_state.soul_ledger.hamartia
            and working_state.soul_ledger.hamartia != "Unformed"
            and working_state.soul_ledger.hamartia_profile is None
        ):
            working_state.soul_ledger.hamartia_profile = get_hamartia_profile(
                working_state.soul_ledger.hamartia
            )

        # Step 3: Process oaths (detect -> parse -> verify)
        oath_broken_id: str | None = None
        broken_ids, fulfilled_ids, transformed_ids = verify_oaths(working_state, action)
        if lachesis_result.oath_violation:
            broken_ids.append(lachesis_result.oath_violation)

        seen_ids: set[str] = set()
        broken_ids = [oath_id for oath_id in broken_ids if not (oath_id in seen_ids or seen_ids.add(oath_id))]
        if broken_ids:
            oath_broken_id = broken_ids[0]

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

        pressure_evolution = evolve_pressures(
            previous_state,
            action,
            outcome,
            proposal_pressure=outcome.pressure_delta,
        )
        outcome.state.pressures = apply_pressure_delta(
            previous_state.pressures,
            pressure_evolution.delta,
            stable_turn=pressure_evolution.stable_turn,
        )
        if outcome.scene_outcome is not None:
            outcome.scene_outcome.pressure_changes = pressure_evolution.delta
            outcome.scene_outcome.pressure_summary = pressure_evolution.summary
        outcome.state.last_action = action

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
        )

    # ------------------------------------------------------------------
    # Shared Pipeline: _finalize_turn (Step 10+)
    # ------------------------------------------------------------------

    async def _finalize_turn(
        self,
        ctx: TurnContext,
        prose: str,
        choices: list[str],
    ) -> TurnResult:
        """Step 10+: Post-prose bookkeeping. Shared by sync and streaming.

        Momus validation → milestone check → prose history append →
        Chronicler compression → RAG indexing → state commit → DB persist.
        """
        outcome = ctx.outcome

        # Momus validation
        validation = await self.momus.validate_prose(prose, outcome.state)
        if not validation.valid:
            logger.warning(f"Momus hallucinations: {validation.hallucinations}")
            prose = validation.corrected_prose or prose
        if validation.law_violations:
            logger.warning(f"Momus law violations: {validation.law_violations}")

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

        # RAG indexing
        try:
            await self.rag.add_turn(
                turn_number=ctx.turn,
                action=ctx.action,
                outcome=outcome.state.last_outcome or "neutral",
                prose_summary=prose[:200],
                environment=outcome.state.session.current_environment,
            )
        except Exception as e:
            logger.warning(f"RAG indexing failed: {e}")

        try:
            outcome.state.rag_context = await self.rag.query(ctx.action, n_results=5)
        except Exception as e:
            logger.warning(f"RAG query failed: {e}")

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
            action=ctx.action,
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
        """Terminal path: epitaph generation + DB persist + death result."""
        self.state = ctx.outcome.state
        _refresh_derived_environment(self.state)
        await self._generate_epitaph(ctx.outcome.state, ctx.turn, ctx.death_reason)

        # DB persist
        await create_turn(
            thread_id=self._thread_id,
            turn_number=ctx.turn,
            action=ctx.action,
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
        )

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

    async def process_turn(self, action: str) -> TurnResult:
        """Execute one full turn through the engine pipeline (sync Clotho)."""
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

        # Clotho generates prose
        clotho_result = await self.clotho.evaluate(
            ctx.outcome.state, action,
            nemesis_desc=ctx.nemesis_desc,
            eris_desc=ctx.eris_desc,
            epoch_phase=ctx.phase,
            stratified_context=ctx.stratified_context,
            vignette_directive=ctx.vignette_directive,
            scene_outcome=ctx.scene_outcome,
        )
        prose, choices = _parse_clotho_output(clotho_result.prose, ctx.phase)
        prose = self._append_interventions(prose, ctx)

        result = await self._finalize_turn(ctx, prose, choices)

        # Dream trigger: fire on Resolution beats (turns 3, 6, 9)
        if ctx.beat_position == "RESOLUTION" and ctx.phase <= 3:
            dream = await self.hypnos.weave_dream(self.state)
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
        db_saved = False
        full_prose_buffer = ""
        ctx: TurnContext | None = None

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
                    "payload": self.state.model_dump(),
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
                await self._handle_death(ctx)
                yield "data: " + json.dumps({
                    "type": "prose",
                    "text": f"**THREAD SEVERED**\n\n{ctx.death_reason}",
                }) + "\n\n"
                yield "data: " + json.dumps({
                    "type": "state",
                    "payload": ctx.outcome.state.model_dump(),
                    "ui_choices": [],
                    "terminal": True,
                    "death_reason": ctx.death_reason,
                }) + "\n\n"
                db_saved = True  # _handle_death persists to DB
                return

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

            # ── PHASE 3: STATE RESOLUTION ────────────────────────
            result = await self._finalize_turn(ctx, prose, choices)
            db_saved = True

            yield "data: " + json.dumps({
                "type": "state",
                "payload": result.state.model_dump(),
                "ui_choices": choices,
                "terminal": False,
                "death_reason": "",
                "nemesis_struck": result.nemesis_struck,
                "eris_struck": result.eris_struck,
                "turn_number": result.turn_number,
            }) + "\n\n"

            # ── PHASE 4: DREAM (epoch boundary only) ──────────────
            if ctx.beat_position == "RESOLUTION" and ctx.phase <= 3:
                dream = await self.hypnos.weave_dream(self.state)
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
            # Guarantee DB persistence even on disconnect
            if not db_saved and self._thread_id and ctx is not None:
                try:
                    await create_turn(
                        thread_id=self._thread_id,
                        turn_number=ctx.turn,
                        action=action,
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
    ) -> None:
        """Generate mythic epitaph + persist to DB.

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

    def reset(self) -> None:
        """Destroy session and reset state."""
        try:
            self.rag.destroy()
        except Exception as e:
            logger.warning(f"RAG cleanup failed: {e}")
        self.rag = NyxRAGStore()
        self.state = ThreadState()
        self._thread_id = None
        logger.info("Kernel reset — new thread begins.")
