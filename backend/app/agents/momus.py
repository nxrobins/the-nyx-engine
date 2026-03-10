"""Momus - The Validator / NER Hallucination Checker v2.0.

Deterministic scan of Clotho's output against Lachesis's state.
Prevents the prose from referencing items, NPCs, or locations
that don't exist in the thread state.

v2.0 changes:
- No inventory to check against; validate environment consistency
- Check soul vector references are plausible
- Oath references must match active oaths
- Phase 3: Full spaCy NER pipeline
"""

from __future__ import annotations

import asyncio
import re

from app.agents.base import AgentBase
from app.schemas.state import MomusValidation, ThreadState


class Momus(AgentBase):
    name = "momus"

    async def evaluate(
        self, state: ThreadState, action: str
    ) -> MomusValidation:
        # Momus doesn't use `action` — it validates prose, not input.
        # This signature satisfies the base class; prose is passed via
        # validate_prose(). For now, always passes in evaluate().
        await asyncio.sleep(0.05)
        return MomusValidation(valid=True)

    async def validate_prose(
        self, prose: str, state: ThreadState
    ) -> MomusValidation:
        """Check Clotho's prose against the thread state for hallucinations."""
        await asyncio.sleep(0.1)

        hallucinations: list[str] = []

        # --- Check 1: Environment consistency ---
        # If prose mentions a specific location type that contradicts the environment
        env_lower = state.session.current_environment.lower()
        prose_lower = prose.lower()

        # Simple heuristic: detect obvious contradictions
        _TERRAIN_PAIRS = [
            ("ocean", "desert"), ("sea", "desert"), ("forest", "ocean"),
            ("mountain", "underwater"), ("cave", "sky"), ("dungeon", "meadow"),
        ]
        for a, b in _TERRAIN_PAIRS:
            if a in env_lower and b in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{b}' but environment is '{a}'-related."
                )
            elif b in env_lower and a in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{a}' but environment is '{b}'-related."
                )

        # --- Check 2: Oath references ---
        # If prose references "your oath" or "sworn", verify oaths exist
        if re.search(r"\b(oath|sworn|vow|promise)\b", prose_lower):
            if not state.soul_ledger.active_oaths:
                hallucinations.append(
                    "Prose references oaths/vows but no active oaths in state."
                )

        # --- Check 3: Death/dying language when soul is healthy ---
        death_words = re.findall(
            r"\b(you die|you are dead|your life ends|you perish)\b", prose_lower
        )
        if death_words:
            vals = list(state.soul_ledger.vectors.model_dump().values())
            if any(v > 3.0 for v in vals):
                hallucinations.append(
                    "Prose declares player death but soul vectors are not collapsed."
                )

        if hallucinations:
            return MomusValidation(
                valid=False,
                hallucinations=hallucinations,
                corrected_prose=prose,  # Phase 3: actually correct it
            )

        return MomusValidation(valid=True, corrected_prose=prose)
