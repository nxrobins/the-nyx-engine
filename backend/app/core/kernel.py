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
- Epoch State Machine (_compute_epoch) controls UI mode + Clotho paragraph count
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
from app.schemas.state import (
    LachesisResponse,
    Oath,
    ThreadState,
    TurnResult,
)
from app.db import (
    ensure_player, create_thread, update_thread_death,
    create_turn, append_chronicle, append_factual_chronicle,
    get_last_ancestor,
)
from app.services import llm
from app.services.bfl import generate_image
from app.services.hamartia_engine import determine_hamartia
from app.services.oath_engine import detect_oath
from app.services.rag import NyxRAGStore
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.kernel")


# ---------------------------------------------------------------------------
# Epoch State Machine
# ---------------------------------------------------------------------------

def _compute_epoch(turn_count: int) -> tuple[int, str]:
    """Epoch state machine. Returns (phase, ui_mode).

    Phase 1 (turns 1-3):  5-6 paragraphs, 3 choices,   buttons
    Phase 2 (turns 4-6):  4-5 paragraphs, 4-5 choices,  buttons
    Phase 3 (turns 7-9):  2-3 paragraphs, 5-6 choices,  buttons
    Phase 4 (turns 10+):  1 paragraph,    0 choices,     open
    """
    if turn_count <= 3:
        return 1, "buttons"
    elif turn_count <= 6:
        return 2, "buttons"
    elif turn_count <= 9:
        return 3, "buttons"
    else:
        return 4, "open"


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

    if not sections:
        return ""

    return "\n\n".join(sections)


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

        # DB: ensure player + create thread
        await ensure_player(player_id)
        self._thread_id = await create_thread(player_id, hamartia)

        # Generate initial prophecy via Nemesis
        nemesis_result = await self.nemesis.generate_initial_prophecy(self.state)
        if nemesis_result.updated_prophecy:
            self.state.the_loom.current_prophecy = nemesis_result.updated_prophecy

        logger.info(f"Prophecy: '{self.state.the_loom.current_prophecy}'")

        # -----------------------------------------------------------
        # Force Turn 1: Clotho generates the actual birth scene
        # -----------------------------------------------------------
        self.state.session.turn_count = 1
        phase, ui_mode = _compute_epoch(1)
        self.state.session.epoch_phase = phase
        self.state.session.ui_mode = ui_mode

        # Tag state so Clotho (mock or real) knows this is a birth scene
        self.state.last_outcome = "birth"

        # Build the birth prompt for Clotho — Age of Ash grounding
        birth_prompt = (
            f"The player's earliest memory is: '{first_memory}'. "
            f"Use this memory to instantly establish their identity in a dark, "
            f"low-fantasy world (The Age of Ash). Tell the player who their "
            f"parents or caretakers are, what their social class or tribe is, "
            f"and what immediate physical event is happening around them right "
            f"now to drive the plot forward. They are age 3."
        )

        # Ancestral echo — flavor for Clotho
        ancestor = await get_last_ancestor(player_id)
        if ancestor and ancestor.get("epitaph"):
            birth_prompt += f" An ancestor's echo haunts this world: '{ancestor['epitaph']}'."
            logger.info(f"Ancestral echo from previous thread (hamartia: {ancestor.get('hamartia')})")

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
        self.state.session.turn_count += 1
        turn = self.state.session.turn_count
        logger.info(f"Turn {turn}: '{action}'")

        # Epoch state machine
        phase, ui_mode = _compute_epoch(turn)
        self.state.session.epoch_phase = phase
        self.state.session.ui_mode = ui_mode
        logger.info(f"Epoch: phase={phase}, ui_mode={ui_mode}")

        # Store last action for reference
        self.state.last_action = action

        # Step 1: Lachesis evaluates state + action validity
        lachesis_result = await self.lachesis.evaluate(self.state, action)

        if not lachesis_result.valid_action:
            logger.info(f"Lachesis BLOCKED: {lachesis_result.reason}")
            self.state.session.turn_count -= 1  # Don't count invalid turns
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
            )

        # Step 2: Apply vector deltas from Lachesis
        working_state = lachesis_result.updated_state or copy.deepcopy(self.state)
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
            logger.info(f"HAMARTIA FORKED: 'Unformed' → '{assigned_hamartia}'")

        # Step 3: Process oaths (detect new, check violations)
        # LLM suggestion takes priority; deterministic engine is the fallback.
        oath_broken_id: str | None = None

        if lachesis_result.oath_violation:
            oath_broken_id = lachesis_result.oath_violation
            for oath in working_state.soul_ledger.active_oaths:
                if oath.oath_id == oath_broken_id:
                    oath.broken = True
                    logger.info(f"Oath BROKEN: {oath.text}")
                    break

        oath_text = lachesis_result.oath_detected or detect_oath(action)
        if oath_text:
            new_oath = Oath(
                oath_id=f"oath_{uuid.uuid4().hex[:8]}",
                text=oath_text,
                turn_sworn=turn,
            )
            working_state.soul_ledger.active_oaths.append(new_oath)
            logger.info(f"New oath sworn: '{new_oath.text}'")

        if lachesis_result.environment_update:
            working_state.session.current_environment = lachesis_result.environment_update

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

        # Set last_outcome for Clotho's context
        if outcome.nemesis_struck:
            outcome.state.last_outcome = "nemesis"
        elif outcome.eris_struck:
            outcome.state.last_outcome = "eris"

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
        await self._generate_epitaph(ctx.outcome.state, ctx.turn)

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
        )
        prose, choices = _parse_clotho_output(clotho_result.prose, ctx.phase)
        prose = self._append_interventions(prose, ctx)

        return await self._finalize_turn(ctx, prose, choices)

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

    async def _generate_epitaph(self, state: ThreadState, turn: int) -> None:
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
        await update_thread_death(self._thread_id, epitaph, turn)

    # ------------------------------------------------------------------
    # Hypnos Stream
    # ------------------------------------------------------------------

    async def get_hypnos_stream(self, action: str):
        """Yield Hypnos filler fragments for SSE streaming."""
        async for fragment in self.hypnos.stream_fragments(self.state, action):
            yield fragment

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
