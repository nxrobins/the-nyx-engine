"""Vignette selection & binding — the engine SELECTS and BINDS, never composes.

Deterministic, model-free (pinned in MODEL_FREE_MODULES): given live state and a
world's authored pool, pick the eligible vignette by the engine's established
hash idiom (min sha256 over player:turn:id — the world-selection convention) and
bind its cast slots to living canon names. A dry pool returns None; the caller
(the kernel, sub-slice 3) falls back to procedural generation LOUDLY.

No-repeat: ThreadState.used_vignette_ids records what this life has already
lived; the caller appends after commit. A life never replays a vignette.
"""

from __future__ import annotations

import hashlib
import logging

from app.schemas.state import ThreadState
from app.schemas.vignette import BoundVignette, Vignette, VignettePool

logger = logging.getLogger("nyx.vignettes")


def _living_name_for_role(state: ThreadState, role: str) -> str | None:
    if not state.canon:
        return None
    for npc in state.canon.npcs.values():
        if npc.role == role and npc.status == "alive":
            return npc.name
    return None


def _eligible(v: Vignette, state: ThreadState) -> bool:
    age = state.session.player_age
    if not (v.min_age <= age <= v.max_age):
        return False
    if v.vignette_id in state.used_vignette_ids:
        return False
    return all(_living_name_for_role(state, role) for role in v.cast_slots)


def select_vignette(state: ThreadState, pool: VignettePool | None) -> BoundVignette | None:
    """Pick and bind this beat's authored vignette, or None (dry pool)."""
    if pool is None or not pool.vignettes:
        return None
    eligible = [v for v in pool.vignettes if _eligible(v, state)]
    if not eligible:
        logger.warning(
            "vignette pool dry for world=%s age=%s used=%d/%d — procedural fallback",
            pool.world_id, state.session.player_age,
            len(state.used_vignette_ids), len(pool.vignettes),
        )
        return None

    seed = f"{state.session.player_id}:{state.session.turn_count}"
    chosen = min(
        eligible,
        key=lambda v: hashlib.sha256(f"{seed}:{v.vignette_id}".encode()).hexdigest(),
    )

    names = {
        role: _living_name_for_role(state, role) or role
        for role in chosen.cast_slots
    }
    situation = chosen.situation
    for role, name in names.items():
        situation = situation.replace("{" + role + "}", name)

    return BoundVignette(
        vignette_id=chosen.vignette_id,
        situation=situation,
        choices=chosen.choices,
        cast_names=names,
    )


def apply_packet(state: ThreadState, bound: BoundVignette, choice_label: str) -> dict:
    """Apply a chosen vignette's typed consequence packet. Deterministic; the
    ENTIRE consequence of a vignette beat (no council — P1-C4/C8).

    Clamps mirror the schema caps (belt + braces, P1-C2): vectors [0,10] via the
    SoulVectorEngine, pressures [0,10], bond via the field's own ±10 bound. The
    scene evolution becomes the new immediate_problem — the stasis-killer. The
    first cast NPC receives the bond delta.

    Returns the receipt: what moved, by how much (lands in the trace slot).
    """
    from app.services.soul_math import SoulVectorEngine  # local: avoid cycles

    choice = next((c for c in bound.choices if c.label == choice_label), None)
    if choice is None:  # dispatch guarantees a match; defensive
        raise ValueError(f"no choice {choice_label!r} on vignette {bound.vignette_id}")
    packet = choice.packet
    receipt: dict = {"vignette_id": bound.vignette_id, "choice": choice_label}

    if packet.vector_deltas:
        state.soul_ledger.vectors = SoulVectorEngine.apply_deltas(
            state.soul_ledger.vectors, packet.vector_deltas
        )
        receipt["vector_deltas"] = dict(packet.vector_deltas)

    if packet.pressure_deltas:
        for key, delta in packet.pressure_deltas.items():
            current = getattr(state.pressures, key)
            setattr(state.pressures, key, max(0.0, min(10.0, current + delta)))
        receipt["pressure_deltas"] = dict(packet.pressure_deltas)

    if packet.bond_delta and bound.cast_names and state.canon:
        first_name = next(iter(bound.cast_names.values()))
        for npc in state.canon.npcs.values():
            if npc.name == first_name and npc.status == "alive":
                npc.bond = max(-10.0, min(10.0, npc.bond + packet.bond_delta))
                receipt["bond"] = {npc.name: packet.bond_delta}
                break

    if packet.scene_evolution and state.canon and state.canon.current_scene:
        state.canon.current_scene.immediate_problem = packet.scene_evolution
        receipt["scene_evolution"] = packet.scene_evolution

    return receipt
