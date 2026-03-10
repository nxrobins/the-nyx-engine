"""The Conflict Resolution Matrix v2.0.

When agents return conflicting flags, the Nyx Kernel resolves them
using this strict hierarchy to prevent deadlock:

Tier 1: LACHESIS (State Validity)  - If invalid, all others muted.
Tier 2: ATROPOS (Finality)         - terminal_state overrides all except Eris miracle.
Tier 3: NEMESIS vs ERIS            - Imbalance tiebreaker: W_c = imbalance - threshold
Tier 4: CLOTHO (Prose)             - Zero logical authority, formats the winner.

v2.0 changes:
- Tiebreaker uses imbalance_score - nemesis_threshold (not hubris)
- No HP/vitality references
- Eris miracle based on low imbalance (balanced soul deserves a break)
- Added prophecy_updated and oath_broken fields
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.schemas.state import (
    AtroposResponse,
    ErisResponse,
    LachesisResponse,
    NemesisResponse,
    ThreadState,
)
from app.services.soul_math import SoulVectorEngine


@dataclass
class ResolvedOutcome:
    """The consensus result after conflict resolution."""
    state: ThreadState
    action_valid: bool = True
    invalid_reason: str = ""
    terminal: bool = False
    death_reason: str = ""
    nemesis_struck: bool = False
    nemesis_description: str = ""
    nemesis_type: str = ""              # "prophecy_update" | "punishment" | "lethal_punishment"
    prophecy_updated: str = ""          # new prophecy text if updated
    vector_penalty: dict = field(default_factory=dict)
    eris_struck: bool = False
    eris_description: str = ""
    vector_chaos: dict = field(default_factory=dict)
    oath_broken: bool = False


class ConflictResolver:
    """Implements the Tier 1-4 conflict resolution hierarchy."""

    def resolve(
        self,
        state: ThreadState,
        lachesis: LachesisResponse,
        atropos: AtroposResponse,
        nemesis: NemesisResponse,
        eris: ErisResponse,
    ) -> ResolvedOutcome:
        # Use Lachesis's updated state as the base
        working_state = lachesis.updated_state or state

        # ----------------------------------------------------------
        # Tier 1: LACHESIS — Absolute State Authority
        # If the action is invalid, everything else is moot.
        # ----------------------------------------------------------
        if not lachesis.valid_action:
            return ResolvedOutcome(
                state=working_state,
                action_valid=False,
                invalid_reason=lachesis.reason,
            )

        # ----------------------------------------------------------
        # Tier 2: ATROPOS — Finality
        # Death overrides all, UNLESS Eris rolls a miracle AND
        # the player's soul is relatively balanced (they deserve
        # a break — low imbalance means they aren't abusing power).
        # ----------------------------------------------------------
        if atropos.terminal_state:
            imbalance = SoulVectorEngine.imbalance_score(
                working_state.soul_ledger.vectors
            )
            # Eris miracle: chaos triggered + balanced soul = saved
            eris_miracle = (
                eris.chaos_triggered
                and imbalance < settings.nemesis_imbalance_threshold
            )
            if not eris_miracle:
                return ResolvedOutcome(
                    state=working_state,
                    terminal=True,
                    death_reason=atropos.death_reason,
                )
            # Eris overrides death — player gets a chaotic reprieve
            return ResolvedOutcome(
                state=working_state,
                terminal=False,
                eris_struck=True,
                eris_description=(
                    f"{eris.chaos_description} "
                    "But in the chaos, death's grip loosens — barely."
                ),
                vector_chaos=eris.vector_chaos,
            )

        # ----------------------------------------------------------
        # Tier 3: NEMESIS vs ERIS — The Tiebreaker
        # W_c = imbalance_score - nemesis_threshold
        # If W_c > 0: Nemesis wins (soul is dangerously imbalanced)
        # If W_c <= 0: Eris wins (soul is balanced, chaos prevails)
        #
        # GOTCHA: Raw imbalance is always positive (0-10), so we
        # subtract the threshold to give Eris a fair chance when
        # the soul is relatively balanced.
        # ----------------------------------------------------------
        both_triggered = nemesis.intervene and eris.chaos_triggered

        if both_triggered:
            imbalance = SoulVectorEngine.imbalance_score(
                working_state.soul_ledger.vectors
            )
            w_c = imbalance - settings.nemesis_imbalance_threshold

            if w_c > 0:
                # Nemesis wins the tiebreaker
                return ResolvedOutcome(
                    state=working_state,
                    nemesis_struck=True,
                    nemesis_description=nemesis.punishment_description,
                    nemesis_type=nemesis.intervention_type,
                    prophecy_updated=nemesis.updated_prophecy,
                    vector_penalty=nemesis.vector_penalty,
                    oath_broken=(nemesis.intervention_type == "lethal_punishment"),
                )
            else:
                # Eris wins — chaos instead of punishment
                return ResolvedOutcome(
                    state=working_state,
                    eris_struck=True,
                    eris_description=eris.chaos_description,
                    vector_chaos=eris.vector_chaos,
                )

        # Only Nemesis triggered
        if nemesis.intervene:
            return ResolvedOutcome(
                state=working_state,
                nemesis_struck=True,
                nemesis_description=nemesis.punishment_description,
                nemesis_type=nemesis.intervention_type,
                prophecy_updated=nemesis.updated_prophecy,
                vector_penalty=nemesis.vector_penalty,
                oath_broken=(nemesis.intervention_type == "lethal_punishment"),
            )

        # Only Eris triggered
        if eris.chaos_triggered:
            return ResolvedOutcome(
                state=working_state,
                eris_struck=True,
                eris_description=eris.chaos_description,
                vector_chaos=eris.vector_chaos,
            )

        # ----------------------------------------------------------
        # Tier 4: No conflicts — clean pass to Clotho
        # ----------------------------------------------------------
        return ResolvedOutcome(state=working_state)
