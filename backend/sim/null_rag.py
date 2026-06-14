"""Frozen, offline RAG substitute for the calibration harness (CAL-E1).

``NyxRAGStore`` wraps ``chromadb.Client()`` and lazily fetches an ONNX
embedding model on first add/query — non-deterministic across machines
(model version / onnxruntime / BLAS / float rounding) and not offline.
The harness swaps it for this no-op so ``rag_context`` stays ``[]`` on
every turn and no embedding model ever loads. One bit: RAG OFF (sim) or
untouched (game).
"""

from __future__ import annotations


class NullRag:
    """A no-op stand-in for NyxRAGStore. Never touches chromadb."""

    def __init__(self, session_id: str | None = None) -> None:
        self._session_id = session_id or "sim"

    async def add_turn(self, *args, **kwargs) -> None:  # noqa: D401 - no-op
        return None

    async def query(self, *args, **kwargs) -> list[str]:
        return []

    def destroy(self) -> None:
        return None
