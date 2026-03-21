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
    AgentProposal,
    AtroposResponse,
    DeliberationTrace,
    ErisResponse,
    LachesisResponse,
    NemesisResponse,
    SceneOutcome,
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
    pressure_delta: dict[str, float] = field(default_factory=dict)
    deliberation_trace: DeliberationTrace | None = None
    scene_outcome: SceneOutcome | None = None


def _vector_summary(vector_patch: dict[str, float]) -> str:
    """Render a compact vector summary for scene outcome text."""
    parts = [f"{name} {value:+.1f}" for name, value in vector_patch.items() if value]
    return ", ".join(parts)


def _fallback_lachesis_proposal(
    state: ThreadState,
    lachesis: LachesisResponse,
) -> AgentProposal:
    """Build a Lachesis proposal if the agent did not provide one."""
    updated = lachesis.updated_state or state
    scene_patch: dict[str, object] = {}
    if lachesis.environment_update:
        scene_patch["environment_update"] = lachesis.environment_update
    if updated.last_outcome:
        scene_patch["outcome_type"] = updated.last_outcome
    if updated.canon and updated.canon.current_scene:
        scene_patch["location_id"] = updated.canon.current_scene.location_id
    return AgentProposal(
        agent="lachesis",
        allow_action=lachesis.valid_action,
        refusal_reason=lachesis.reason,
        scene_patch=scene_patch,
        vector_patch=dict(lachesis.vector_deltas),
        intervention_copy=lachesis.reason if not lachesis.valid_action else "",
        priority_note="State validity, continuity, and grounded consequence.",
        confidence=1.0 if not lachesis.valid_action else 0.95,
    )


def _fallback_atropos_proposal(atropos: AtroposResponse) -> AgentProposal:
    """Build an Atropos proposal if the agent did not provide one."""
    return AgentProposal(
        agent="atropos",
        allow_action=True,
        scene_patch={"warning": atropos.death_reason} if atropos.death_reason else {},
        death_flag=atropos.terminal_state,
        death_reason=atropos.death_reason if atropos.terminal_state else "",
        intervention_copy=atropos.death_reason,
        priority_note="Finality and irreversible consequence.",
        confidence=1.0 if atropos.terminal_state else 0.8,
    )


def _fallback_nemesis_proposal(nemesis: NemesisResponse) -> AgentProposal:
    """Build a Nemesis proposal if the agent did not provide one."""
    scene_patch: dict[str, object] = {}
    if nemesis.intervention_type:
        scene_patch["intervention_type"] = nemesis.intervention_type
    if nemesis.updated_prophecy:
        scene_patch["updated_prophecy"] = nemesis.updated_prophecy
    if nemesis.punishment_description:
        scene_patch["punishment_description"] = nemesis.punishment_description
    return AgentProposal(
        agent="nemesis",
        allow_action=True,
        scene_patch=scene_patch,
        vector_patch=dict(nemesis.vector_penalty),
        prophecy_patch=nemesis.updated_prophecy,
        intervention_copy=nemesis.punishment_description or nemesis.updated_prophecy,
        priority_note="Judgment, prophecy, and karmic rebalancing.",
        confidence=0.85 if nemesis.intervene else 0.45,
    )


def _fallback_eris_proposal(eris: ErisResponse) -> AgentProposal:
    """Build an Eris proposal if the agent did not provide one."""
    scene_patch = {}
    if eris.chaos_triggered:
        scene_patch = {
            "chaos_description": eris.chaos_description,
            "chaos_severity": eris.chaos_severity,
        }
    return AgentProposal(
        agent="eris",
        allow_action=True,
        scene_patch=scene_patch,
        vector_patch=dict(eris.vector_chaos),
        intervention_copy=eris.chaos_description,
        priority_note="Instability, wildcard disruption, and misrule.",
        confidence=0.7 if eris.chaos_triggered else 0.4,
    )


def _present_npc_names(state: ThreadState) -> list[str]:
    """Return alive present NPC names from the canonical scene."""
    if not state.canon or not state.canon.current_scene:
        return []

    names: list[str] = []
    for npc_id in state.canon.current_scene.present_npc_ids:
        npc = state.canon.npcs.get(npc_id)
        if npc and npc.status == "alive":
            names.append(npc.name)
    return names


def _apply_intervention_to_scene(state: ThreadState, text: str) -> None:
    """Persist the winning intervention into the canonical scene."""
    if not text or not state.canon or not state.canon.current_scene:
        return
    state.canon.current_scene.carryover_consequence = text


def _merge_pressure_patches(
    proposals: list[AgentProposal],
    winner_order: list[str],
) -> dict[str, float]:
    """Merge pressure patches from the agents that materially won the turn."""
    merged: dict[str, float] = {}
    winners = set(winner_order)
    for proposal in proposals:
        if proposal.agent not in winners:
            continue
        for key, value in proposal.pressure_patch.items():
            merged[key] = merged.get(key, 0.0) + value
    return {
        key: round(value, 2)
        for key, value in merged.items()
        if abs(value) >= 0.05
    }


def _build_scene_outcome(
    state: ThreadState,
    proposals: list[AgentProposal],
    outcome: ResolvedOutcome,
) -> SceneOutcome:
    """Assemble the resolved scene contract Clotho must obey."""
    material_changes: list[str] = []

    for proposal in proposals:
        if proposal.agent == "lachesis" and proposal.vector_patch:
            summary = _vector_summary(proposal.vector_patch)
            if summary:
                material_changes.append(f"Soul movement: {summary}")

    if outcome.nemesis_struck and outcome.nemesis_description:
        material_changes.append(outcome.nemesis_description)
    if outcome.eris_struck and outcome.eris_description:
        material_changes.append(outcome.eris_description)
    if outcome.prophecy_updated:
        material_changes.append(f"Prophecy shifts: {outcome.prophecy_updated}")
    if outcome.terminal and outcome.death_reason:
        material_changes.append(outcome.death_reason)
    if outcome.pressure_delta:
        material_changes.append(
            "Pressure shifts: " + _vector_summary(outcome.pressure_delta)
        )

    present_npcs = _present_npc_names(state)

    immediate_problem = state.session.current_environment
    if state.canon and state.canon.current_scene:
        immediate_problem = (
            state.canon.current_scene.carryover_consequence
            or state.canon.current_scene.immediate_problem
            or immediate_problem
        )

    intervening_fates: list[str] = []
    if outcome.nemesis_struck:
        intervening_fates.append("nemesis")
    if outcome.eris_struck:
        intervening_fates.append("eris")
    if outcome.terminal:
        intervening_fates.append("atropos")

    must_not_contradict: list[str] = []
    if state.session.current_environment:
        must_not_contradict.append(f"Environment: {state.session.current_environment}")
    if present_npcs:
        must_not_contradict.append("Present NPCs: " + ", ".join(present_npcs))
    if state.canon and state.canon.current_scene and state.canon.current_scene.scene_objective:
        must_not_contradict.append(
            "Scene objective: " + state.canon.current_scene.scene_objective
        )
    if outcome.prophecy_updated:
        must_not_contradict.append("Updated prophecy must remain true this turn.")

    return SceneOutcome(
        material_changes=material_changes,
        present_npcs=present_npcs,
        immediate_problem=immediate_problem,
        intervening_fates=intervening_fates,
        must_not_contradict=must_not_contradict,
        pressure_changes=outcome.pressure_delta,
    )


def _finalize_outcome(
    outcome: ResolvedOutcome,
    proposals: list[AgentProposal],
    winner_order: list[str],
    final_reason: str,
) -> ResolvedOutcome:
    """Attach trace + resolved scene contract to the outcome."""
    if outcome.terminal and outcome.death_reason:
        _apply_intervention_to_scene(outcome.state, outcome.death_reason)
    elif outcome.nemesis_struck and outcome.nemesis_description:
        _apply_intervention_to_scene(outcome.state, outcome.nemesis_description)
    elif outcome.eris_struck and outcome.eris_description:
        _apply_intervention_to_scene(outcome.state, outcome.eris_description)

    trace = DeliberationTrace(
        turn_number=outcome.state.session.turn_count,
        proposals=proposals,
        winner_order=winner_order,
        final_reason=final_reason,
    )
    outcome.pressure_delta = _merge_pressure_patches(proposals, winner_order)
    outcome.state.recent_traces.append(trace)
    outcome.state.recent_traces = outcome.state.recent_traces[-8:]
    outcome.deliberation_trace = trace
    outcome.scene_outcome = _build_scene_outcome(outcome.state, proposals, outcome)
    return outcome


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
        proposals = [
            lachesis.proposal or _fallback_lachesis_proposal(state, lachesis),
            atropos.proposal or _fallback_atropos_proposal(atropos),
            nemesis.proposal or _fallback_nemesis_proposal(nemesis),
            eris.proposal or _fallback_eris_proposal(eris),
        ]

        # ----------------------------------------------------------
        # Tier 1: LACHESIS — Absolute State Authority
        # If the action is invalid, everything else is moot.
        # ----------------------------------------------------------
        if not lachesis.valid_action:
            return _finalize_outcome(ResolvedOutcome(
                state=working_state,
                action_valid=False,
                invalid_reason=lachesis.reason,
            ), proposals, ["lachesis"], "Lachesis rejected the action as invalid.")

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
                return _finalize_outcome(ResolvedOutcome(
                    state=working_state,
                    terminal=True,
                    death_reason=atropos.death_reason,
                ), proposals, ["lachesis", "atropos"], "Atropos overrode all other claims with finality.")
            # Eris overrides death — player gets a chaotic reprieve
            return _finalize_outcome(ResolvedOutcome(
                state=working_state,
                terminal=False,
                eris_struck=True,
                eris_description=(
                    f"{eris.chaos_description} "
                    "But in the chaos, death's grip loosens — barely."
                ),
                vector_chaos=eris.vector_chaos,
            ), proposals, ["lachesis", "eris"], "Eris forced a miracle because the soul remained balanced enough to deserve one.")

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
                return _finalize_outcome(ResolvedOutcome(
                    state=working_state,
                    nemesis_struck=True,
                    nemesis_description=nemesis.punishment_description,
                    nemesis_type=nemesis.intervention_type,
                    prophecy_updated=nemesis.updated_prophecy,
                    vector_penalty=nemesis.vector_penalty,
                    oath_broken=(nemesis.intervention_type == "lethal_punishment"),
                ), proposals, ["lachesis", "nemesis"], "Nemesis won the tiebreaker because the soul was too imbalanced for chaos to excuse.")
            else:
                # Eris wins — chaos instead of punishment
                return _finalize_outcome(ResolvedOutcome(
                    state=working_state,
                    eris_struck=True,
                    eris_description=eris.chaos_description,
                    vector_chaos=eris.vector_chaos,
                ), proposals, ["lachesis", "eris"], "Eris won the tiebreaker because the soul remained balanced enough for chaos to prevail.")

        # Only Nemesis triggered
        if nemesis.intervene:
            return _finalize_outcome(ResolvedOutcome(
                state=working_state,
                nemesis_struck=True,
                nemesis_description=nemesis.punishment_description,
                nemesis_type=nemesis.intervention_type,
                prophecy_updated=nemesis.updated_prophecy,
                vector_penalty=nemesis.vector_penalty,
                oath_broken=(nemesis.intervention_type == "lethal_punishment"),
            ), proposals, ["lachesis", "nemesis"], "Nemesis intervened uncontested.")

        # Only Eris triggered
        if eris.chaos_triggered:
            return _finalize_outcome(ResolvedOutcome(
                state=working_state,
                eris_struck=True,
                eris_description=eris.chaos_description,
                vector_chaos=eris.vector_chaos,
            ), proposals, ["lachesis", "eris"], "Eris intervened uncontested.")

        # ----------------------------------------------------------
        # Tier 4: No conflicts — clean pass to Clotho
        # ----------------------------------------------------------
        return _finalize_outcome(
            ResolvedOutcome(state=working_state),
            proposals,
            ["lachesis"],
            "No higher Fate overruled the grounded state judgment.",
        )
