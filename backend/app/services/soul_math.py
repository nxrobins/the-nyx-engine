"""Soul Vector Engine — The Mathematical Framework v2.0.

Replaces HubrisCalculator + NarrativeStabilityTracker with a unified
soul vector algebra. All game math flows through this engine.

Core concept: Four soul vectors (Metis, Bia, Kleos, Aidos) range 0-10.
Imbalance between them drives Nemesis intervention. Milestones fire
when any vector hits 10. Death occurs when all vectors collapse to ≤ 1.
"""

from __future__ import annotations

from app.schemas.state import SoulVectors


class SoulVectorEngine:
    """Pure-function engine for soul vector math. No mutable state."""

    @staticmethod
    def apply_deltas(
        vectors: SoulVectors, deltas: dict[str, float]
    ) -> SoulVectors:
        """Apply delta changes and clamp each vector to [0, 10]."""
        data = vectors.model_dump()
        for key, delta in deltas.items():
            if key in data:
                data[key] = max(0.0, min(10.0, data[key] + delta))
        return SoulVectors(**data)

    @staticmethod
    def dominant_vector(vectors: SoulVectors) -> str:
        """Return the name of the highest soul vector."""
        data = vectors.model_dump()
        return max(data, key=data.get)

    @staticmethod
    def weakest_vector(vectors: SoulVectors) -> str:
        """Return the name of the lowest soul vector."""
        data = vectors.model_dump()
        return min(data, key=data.get)

    @staticmethod
    def imbalance_score(vectors: SoulVectors) -> float:
        """max(vectors) - min(vectors). Range: 0.0 to 10.0."""
        vals = list(vectors.model_dump().values())
        return max(vals) - min(vals)

    @staticmethod
    def should_nemesis_watch(
        vectors: SoulVectors, threshold: float = 6.0
    ) -> bool:
        """True when soul imbalance exceeds the Nemesis threshold."""
        return SoulVectorEngine.imbalance_score(vectors) >= threshold

    @staticmethod
    def is_milestone(vectors: SoulVectors) -> tuple[bool, str]:
        """Check if any vector has reached 10.

        Returns (True, "vector_name") or (False, "").
        """
        data = vectors.model_dump()
        for name, val in data.items():
            if val >= 10.0:
                return True, name
        return False, ""

    @staticmethod
    def is_dead_soul(vectors: SoulVectors) -> bool:
        """True when all vectors have collapsed to ≤ 1.0."""
        return all(v <= 1.0 for v in vectors.model_dump().values())

    @staticmethod
    def vector_summary(vectors: SoulVectors) -> str:
        """Human-readable summary for debug/logging."""
        d = vectors.model_dump()
        parts = [f"{k}={v:.1f}" for k, v in d.items()]
        return " | ".join(parts)
