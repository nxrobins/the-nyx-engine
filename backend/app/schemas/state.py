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


class Oath(BaseModel):
    """A promise the player has sworn. Breaking it invokes Nemesis."""
    oath_id: str
    text: str              # the raw sworn text
    turn_sworn: int
    broken: bool = False


class SoulLedger(BaseModel):
    """The player's soul state — replaces HP/Inventory."""
    hamartia: str = ""     # tragic flaw, immutable after Turn 0
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
    current_environment: str = "A shadowed threshold between worlds."
    epoch_phase: int = 1        # 1-4, computed from turn_count
    ui_mode: str = "buttons"    # "buttons" | "open"


# ---------------------------------------------------------------------------
# The Thread State (master game state per session)
# ---------------------------------------------------------------------------

class ThreadState(BaseModel):
    """The single source of truth maintained by Lachesis."""
    session: SessionData = Field(default_factory=SessionData)
    soul_ledger: SoulLedger = Field(default_factory=SoulLedger)
    the_loom: TheLoom = Field(default_factory=TheLoom)
    rag_context: list[str] = Field(default_factory=list)  # fallback context
    last_action: str = ""
    last_outcome: str = ""
    # Chronicler: rolling prose buffer + compressed chronicle
    prose_history: list[str] = Field(default_factory=list)   # last N raw prose turns
    chronicle: list[str] = Field(default_factory=list)       # mythic sentence per 5-turn window


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


class AtroposResponse(BaseModel):
    """Atropos checks for terminal conditions.
    Triggers: oath_broken, narrative_dead_end, self_destruction, dead_soul."""
    terminal_state: bool = False
    death_reason: str = ""


class NemesisResponse(BaseModel):
    """Nemesis manages prophecy and punishment."""
    intervene: bool = False
    intervention_type: str = ""         # "prophecy_update" | "punishment" | "lethal_punishment"
    updated_prophecy: str = ""
    punishment_description: str = ""
    vector_penalty: dict[str, float] = Field(default_factory=dict)


class ErisResponse(BaseModel):
    """Eris rolls for chaos injection with vector disruption."""
    chaos_triggered: bool = False
    chaos_description: str = ""
    chaos_severity: float = 0.0
    vector_chaos: dict[str, float] = Field(default_factory=dict)


class ClothoResponse(BaseModel):
    """Clotho generates the narrative prose."""
    prose: str = ""
    scene_tags: list[str] = Field(default_factory=list)
    ui_choices: list[str] = Field(default_factory=list)


class MomusValidation(BaseModel):
    """Momus validates Clotho's output against state."""
    valid: bool = True
    hallucinations: list[str] = Field(default_factory=list)
    corrected_prose: str = ""


class ChroniclerResponse(BaseModel):
    """Chronicler compresses N turns into one mythic sentence."""
    chronicle_sentence: str = ""


class HypnosResponse(BaseModel):
    """Hypnos generates atmospheric filler text for latency masking."""
    filler_text: str = ""


# ---------------------------------------------------------------------------
# Kernel I/O
# ---------------------------------------------------------------------------

class PlayerAction(BaseModel):
    """Incoming player action."""
    action: str
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
    prose: str
    state: ThreadState
    terminal: bool = False
    death_reason: str = ""
    nemesis_struck: bool = False
    eris_struck: bool = False
    turn_number: int = 0
    image_url: str = ""    # populated if BFL generated a milestone image
    ui_choices: list[str] = Field(default_factory=list)
