"""The Thread Data Schema v2.0 — Soul Ledger.

Replaces HP/Mana/Inventory with four soul vectors (Metis, Bia, Kleos, Aidos),
an oath system, and a dynamic prophecy. Pydantic enforces the contract so
agents can't corrupt the thread.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Soul Ledger Sub-models
# ---------------------------------------------------------------------------

class SoulVectors(BaseModel):
    """Four dimensions of the player's soul. Range: 0.0 - 10.0 each."""
    metis: float = 5.0    # cunning, intellect, strategy
    bia: float = 5.0      # force, violence, aggression
    kleos: float = 5.0    # glory, fame, public renown
    aidos: float = 5.0    # shadow, restraint, humility


class OathTerms(BaseModel):
    """Structured oath terms extracted from oath language."""
    subject: str = ""
    promised_action: str = ""
    protected_target: str | None = None
    forbidden_action: str | None = None
    deadline: str | None = None
    witness: str | None = None
    price: str | None = None


class Oath(BaseModel):
    """A promise the player has sworn. Breaking it invokes Nemesis."""
    oath_id: str
    text: str              # the raw sworn text
    turn_sworn: int
    broken: bool = False
    terms: OathTerms | None = None
    status: str = "active"   # active | fulfilled | broken | transformed
    fulfillment_note: str = ""


class HamartiaProfile(BaseModel):
    """Mechanical profile applied once a tragic flaw hardens into fate."""
    name: str
    choice_bias: str
    nemesis_multiplier: float = 1.0
    eris_bias: float = 0.0
    style_directive: str = ""
    refusal_pattern: str = ""
    social_cost_bias: str = ""


class SoulLedger(BaseModel):
    """The player's soul state — replaces HP/Inventory."""
    hamartia: str = ""     # tragic flaw, immutable after Turn 0
    hamartia_profile: HamartiaProfile | None = None
    vectors: SoulVectors = Field(default_factory=SoulVectors)
    active_oaths: list[Oath] = Field(default_factory=list)


class TheLoom(BaseModel):
    """Prophecy and milestone tracking — replaces Hubris gauge."""
    current_prophecy: str = ""
    milestone_reached: bool = False
    image_prompt_trigger: str = ""    # set when a vector hits 10


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionData(BaseModel):
    player_id: str = "usr_001"
    player_name: str = "Stranger"
    player_gender: str = "unknown"
    first_memory: str = ""
    turn_count: int = 0
    run_number: int = 1
    current_environment: str = ""
    epoch_phase: int = 1        # 1-4, computed from turn_count
    ui_mode: str = "buttons"    # "buttons" | "open"
    player_age: int = 3         # deterministic age per turn
    beat_position: str = "SETUP"  # SETUP | COMPLICATION | RESOLUTION | OPEN


# ---------------------------------------------------------------------------
# Canonical World State
# ---------------------------------------------------------------------------

class CanonNPC(BaseModel):
    """A named person in the world canon."""
    npc_id: str
    name: str
    role: str
    home_location_id: str
    current_location_id: str
    status: str = "alive"  # alive | dead | missing | departed
    trust: float = 0.0
    fear: float = 0.0
    obligation: float = 0.0
    tags: list[str] = Field(default_factory=list)
    last_seen_turn: int = 0


class CanonLocation(BaseModel):
    """A stable place in the world canon."""
    location_id: str
    name: str
    region: str
    kind: str
    current_condition: str = ""
    tags: list[str] = Field(default_factory=list)


class CanonFaction(BaseModel):
    """A social or political force in the world canon."""
    faction_id: str
    name: str
    stance: str = "neutral"
    leverage: float = 0.0
    hostility: float = 0.0
    notes: str = ""


class SceneClock(BaseModel):
    """A simple progress tracker for unresolved scene pressure."""
    clock_id: str
    label: str
    progress: int = 0
    max_segments: int = 4
    stakes: str = ""
    resolution_hint: str = ""


class SceneState(BaseModel):
    """The immediate playable scene."""
    scene_id: str
    location_id: str
    present_npc_ids: list[str] = Field(default_factory=list)
    active_clock_ids: list[str] = Field(default_factory=list)
    immediate_problem: str = ""
    scene_objective: str = ""
    carryover_consequence: str = ""


class WorldCanon(BaseModel):
    """Structured world state that outlives prose."""
    npcs: dict[str, CanonNPC] = Field(default_factory=dict)
    locations: dict[str, CanonLocation] = Field(default_factory=dict)
    factions: dict[str, CanonFaction] = Field(default_factory=dict)
    clocks: dict[str, SceneClock] = Field(default_factory=dict)
    current_scene: SceneState | None = None
    world_facts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deliberation + Resolved Scene Contracts
# ---------------------------------------------------------------------------

class AgentProposal(BaseModel):
    """A single agent's structured bid for what should become true."""
    agent: str
    allow_action: bool = True
    refusal_reason: str = ""
    scene_patch: dict[str, object] = Field(default_factory=dict)
    vector_patch: dict[str, float] = Field(default_factory=dict)
    pressure_patch: dict[str, float] = Field(default_factory=dict)
    prophecy_patch: str = ""
    death_flag: bool = False
    death_reason: str = ""
    intervention_copy: str = ""
    priority_note: str = ""
    confidence: float = 0.5


class DeliberationTrace(BaseModel):
    """A compact record of how the Fates judged the turn."""
    turn_number: int
    proposals: list[AgentProposal] = Field(default_factory=list)
    winner_order: list[str] = Field(default_factory=list)
    final_reason: str = ""


class SceneOutcome(BaseModel):
    """Canonical facts Clotho must narrate without contradiction."""
    material_changes: list[str] = Field(default_factory=list)
    present_npcs: list[str] = Field(default_factory=list)
    immediate_problem: str = ""
    intervening_fates: list[str] = Field(default_factory=list)
    must_not_contradict: list[str] = Field(default_factory=list)
    pressure_changes: dict[str, float] = Field(default_factory=dict)
    pressure_summary: str = ""


# ---------------------------------------------------------------------------
# Pressure + Legacy
# ---------------------------------------------------------------------------

class PressureState(BaseModel):
    """External consequences that push back on the player each turn."""
    suspicion: float = 0.0
    scarcity: float = 0.0
    wounds: float = 0.0
    debt: float = 0.0
    faction_heat: float = 0.0
    omen: float = 0.0
    exploit_score: float = 0.0
    stability_streak: int = 0


class LegacyEcho(BaseModel):
    """A surviving mark from a prior dead thread."""
    source_thread_id: str
    epitaph: str
    hamartia: str
    inherited_mark: str
    mechanical_effect: str


# ---------------------------------------------------------------------------
# The Thread State (master game state per session)
# ---------------------------------------------------------------------------

class ThreadState(BaseModel):
    """The single source of truth maintained by Lachesis."""
    session: SessionData = Field(default_factory=SessionData)
    soul_ledger: SoulLedger = Field(default_factory=SoulLedger)
    the_loom: TheLoom = Field(default_factory=TheLoom)
    pressures: PressureState = Field(default_factory=PressureState)
    canon: WorldCanon | None = None
    rag_context: list[str] = Field(default_factory=list)  # fallback context
    world_context: str = ""    # formatted world seed, fed to Clotho every turn
    last_action: str = ""
    last_outcome: str = ""
    current_dream: str = ""    # Hypnos dream text (consumed by next Clotho call)
    # Chronicler: rolling prose buffer + dual-track compressed chronicle
    prose_history: list[str] = Field(default_factory=list)       # last N raw prose turns
    chronicle: list[str] = Field(default_factory=list)           # mythic sentence per 5-turn window
    factual_chronicle: list[str] = Field(default_factory=list)   # factual state snapshots per window
    recent_traces: list[DeliberationTrace] = Field(default_factory=list)
    legacy_echoes: list[LegacyEcho] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Response Models
# ---------------------------------------------------------------------------

class LachesisResponse(BaseModel):
    """Lachesis evaluates action validity, classifies soul vector deltas,
    detects oaths, and updates environment."""
    valid_action: bool = True
    reason: str = ""
    updated_state: Optional[ThreadState] = None
    vector_deltas: dict[str, float] = Field(default_factory=dict)
    oath_detected: Optional[str] = None       # raw oath text if sworn
    oath_violation: Optional[str] = None      # oath_id if action violates
    environment_update: str = ""              # new environment description
    assigned_hamartia: Optional[str] = None   # set at Turn 10 when "Unformed"
    proposal: AgentProposal | None = None


class AtroposResponse(BaseModel):
    """Atropos checks for terminal conditions.
    Triggers: oath_broken, narrative_dead_end, self_destruction, dead_soul."""
    terminal_state: bool = False
    death_reason: str = ""
    proposal: AgentProposal | None = None


class NemesisResponse(BaseModel):
    """Nemesis manages prophecy and punishment."""
    intervene: bool = False
    intervention_type: str = ""         # "prophecy_update" | "punishment" | "lethal_punishment"
    updated_prophecy: str = ""
    punishment_description: str = ""
    vector_penalty: dict[str, float] = Field(default_factory=dict)
    proposal: AgentProposal | None = None


class ErisResponse(BaseModel):
    """Eris rolls for chaos injection with vector disruption."""
    chaos_triggered: bool = False
    chaos_description: str = ""
    chaos_severity: float = 0.0
    vector_chaos: dict[str, float] = Field(default_factory=dict)
    proposal: AgentProposal | None = None


class ClothoResponse(BaseModel):
    """Clotho generates the narrative prose."""
    prose: str = ""
    scene_tags: list[str] = Field(default_factory=list)
    ui_choices: list[str] = Field(default_factory=list)


class MomusValidation(BaseModel):
    """Momus validates Clotho's output against state.

    hallucinations — factual contradictions against thread state (env, oaths, death).
    law_violations — breaches of the Laws of the Loom (literary style rules).
    """
    valid: bool = True
    hallucinations: list[str] = Field(default_factory=list)
    law_violations: list[str] = Field(default_factory=list)
    corrected_prose: str = ""


class ChroniclerResponse(BaseModel):
    """Chronicler compresses N turns into dual-track output.

    chronicle_sentence — mythic track: poetic one-sentence compression of internal change.
    factual_digest — factual track: deterministic state snapshot for consistency.
    """
    chronicle_sentence: str = ""
    factual_digest: str = ""


class HypnosResponse(BaseModel):
    """Hypnos generates atmospheric filler text for latency masking."""
    filler_text: str = ""


# ---------------------------------------------------------------------------
# Kernel I/O
# ---------------------------------------------------------------------------

class PlayerAction(BaseModel):
    """Incoming player action."""
    action: str
    session_id: str = ""     # required for session isolation
    player_id: str = "usr_001"


class InitRequest(BaseModel):
    """Session initialization — choose your tragic flaw."""
    hamartia: str
    player_id: str = "usr_001"
    name: str = "Stranger"
    gender: str = "unknown"
    first_memory: str = ""


class TurnResult(BaseModel):
    """Final output of a complete turn through the Nyx Kernel."""
    session_id: str = ""     # returned on init, sent back on every turn
    prose: str
    state: ThreadState
    terminal: bool = False
    death_reason: str = ""
    nemesis_struck: bool = False
    eris_struck: bool = False
    turn_number: int = 0
    image_url: str = ""    # populated if BFL generated a milestone image
    ui_choices: list[str] = Field(default_factory=list)
