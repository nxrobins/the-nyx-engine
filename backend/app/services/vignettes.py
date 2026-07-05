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
