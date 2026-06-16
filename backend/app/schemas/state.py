"""The Thread Data Schema v2.0 — Soul Ledger.

Replaces HP/Mana/Inventory with four soul vectors (Metis, Bia, Kleos, Aidos),
an oath system, and a dynamic prophecy. Pydantic enforces the contract so
agents can't corrupt the thread.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.morpheus import Promise


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

class NPCEvent(BaseModel):
    """One compressed memory of what the player did to an NPC.

    Deterministic: the note is a template, never a model write. The events
    ring is SURFACING-only — the compounding betrayal math reads the dedicated
    CanonNPC.betrayal_count integer, never this lossy list (Depth: E6).
    """
    turn: int = 0
    kind: str = "neutral"   # betrayed|harmed|coerced|aided|protected|confided|honored|neutral
    valence: float = Field(default=0.0, ge=-2.0, le=2.0)
    note: str = ""          # <= 80 chars; deterministic template, never a model write


class ArrivalCondition(BaseModel):
    """A machine-checkable predicate for when a LATENT NPC enters the life.

    Conjunctive over the NON-DEFAULT gates: every gate that is set must hold,
    and at least one must be set (an all-default condition is vacuous and never
    fires — friction must be earned). The gates read ONLY canon + turn, never
    soul/pressures/doom, so arrival stays a pure function of canon. Authored,
    never model-invented (The Witnesses Arrive).
    """
    min_turn: int = Field(default=0, ge=0, le=200)
    requires_bond_npc_id: str = Field(default="", max_length=80)
    requires_bond_at_least: float = Field(default=0.0, ge=-10.0, le=10.0)
    on_clock_resolved: str = Field(default="", max_length=80)
    arrival_priority: int = Field(default=0, ge=0, le=99)  # author tiebreak; lower arrives first


class CanonNPC(BaseModel):
    """A named person in the world canon."""
    npc_id: str
    name: str
    role: str
    home_location_id: str
    current_location_id: str
    status: str = "alive"  # alive | dead | missing | departed | latent
    trust: float = 0.0
    fear: float = 0.0
    obligation: float = 0.0
    tags: list[str] = Field(default_factory=list)
    last_seen_turn: int = 0
    # The turn this NPC departed (status -> "departed"), or 0 if they never have.
    # Lets Momus grant a departing witness their named goodbye on the leaving
    # turn while still flagging them as absent on every turn after.
    departed_turn: int = 0
    # Depth: the populated mind — authored want + a friction-weighted memory.
    want: str = ""                                   # standing desire, authored, immutable at runtime
    bond: float = Field(default=0.0, ge=-10.0, le=10.0)   # trajectory; sours fast, warms slow
    betrayal_weight: float = Field(default=0.0, ge=0.0, le=10.0)  # monotone; never decremented
    betrayal_count: int = Field(default=0, ge=0, le=99)          # monotone tally; compounding reads THIS
    events: list[NPCEvent] = Field(default_factory=list)         # bounded ring (EVENT_CAP)
    # The Witnesses Arrive: a "latent" NPC is authored but NOT present at birth;
    # it enters the life when its arrival_condition is met (see maybe_arrive_npcs).
    # arrived_turn stamps the entry (0 = never arrived). Both default so every
    # pre-existing NPC and serialized thread round-trips unchanged.
    arrival_condition: ArrivalCondition | None = None
    arrived_turn: int = 0


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
    lethal: bool = False   # a fired lethal clock starts a doom sequence
    # The World Takes: a fired clock with a named target claims that NPC's life
    # (canonical npc_id, e.g. "npc_maren"). Authored + immutable after bootstrap;
    # default "" is a pure no-op. NEVER both lethal and claiming (cartridge rejects).
    claims_npc_id: str = ""


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
# Doom — staged death sentences
# ---------------------------------------------------------------------------

class DoomState(BaseModel):
    """A staged death sentence. Once active it advances every turn.

    Inescapable dooms (broken oaths) cannot be lifted — the player gets
    the gap between transgression and ruin, not a reprieve. Escapable
    dooms (wounds, faction heat) lift when their cause is answered.
    Atropos severs the thread when stage reaches max_stage.
    """
    active: bool = False
    cause: str = ""           # "broken_oath" | "wounds" | "faction_heat" | "clock"
    description: str = ""     # what the doom is, in prose-usable terms
    stage: int = 0
    max_stage: int = 3
    started_turn: int = 0
    escapable: bool = False
    escape_hint: str = ""     # what would lift it (surfaced to prose/choices)


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
    doom: DoomState = Field(default_factory=DoomState)
    rag_context: list[str] = Field(default_factory=list)  # fallback context
    world_context: str = ""    # formatted world seed, fed to Clotho every turn
    last_action: str = ""
    last_outcome: str = ""
    current_dream: str = ""    # Hypnos dream text (consumed by next Clotho call)
    craft_notes: list[str] = Field(default_factory=list)  # Momus law violations fed to next Clotho call
    # Morpheus P2: the Promise Ledger — typed narrative obligations
    # (plants with payoff windows). Audited each turn; rendered into
    # Clotho's context; read by Hypnos for dreams and Nemesis for irony.
    ledger: list["Promise"] = Field(default_factory=list)
    # Scribe P3: the voice this life's book is written in — discovered
    # at the Fork from hamartia + soul trajectory, fixed thereafter.
    life_voice: str = ""
    # Assayer P4: which world this life was born into (cartridge world_id
    # or "builtin-{archetype}"). The verdict's primary key.
    world_id: str = ""
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
    # The Vigil: a death that originated from a self-destruction keyword is
    # exempt from the Eris miracle — a vulnerable player who types real-world
    # self-harm framing must never get a "the dice saved you" reprieve. The
    # fiction stays cruel to the character; this only hardens permanence.
    self_destruction_origin: bool = False
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
    repair_needed: bool = False
    repair_brief: str = ""
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

# The largest action the request layer accepts. Kept equal to welfare._SCAN_CAP
# (the crisis detector canonicalizes + scans at most this many chars): rejecting
# anything longer HERE means genuine ideation can never ride in past the scan
# window into a durable store unredacted (audit M3 follow-up). A literal, not an
# import, so the schema layer stays free of the services layer.
MAX_ACTION_CHARS = 65_536


class PlayerAction(BaseModel):
    """Incoming player action."""
    action: str = Field(max_length=MAX_ACTION_CHARS)
    session_id: str = ""     # required for session isolation
    player_id: str = "usr_001"
    content_prefs: dict | None = None   # The Vigil: self-asserted consent (carried, not yet acted on)


class InitRequest(BaseModel):
    """Session initialization — choose your tragic flaw."""
    hamartia: str
    player_id: str = "usr_001"
    name: str = "Stranger"
    gender: str = "unknown"
    first_memory: str = ""
    content_prefs: dict | None = None   # The Vigil: self-asserted consent (carried, not yet acted on)


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
    book_id: str = ""      # Scribe P3: set on death when the life was bound
    epitaph: str = ""      # The Witness: the carved line, shown in the Death Rite
    crisis_resources: dict | None = None  # The Vigil: static care payload on a flagged turn (gated)
