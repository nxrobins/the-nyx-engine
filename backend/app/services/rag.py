"""ChromaDB RAG Store — Ephemeral per-session vector search.

Each game session gets its own ChromaDB collection (in-memory).
Destroyed on game reset. Provides semantic search over past turns
so Lachesis can retrieve relevant context without a growing list.

GOTCHA: ChromaDB's ephemeral client is synchronous. All calls are
wrapped in asyncio.to_thread() to avoid blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import chromadb

logger = logging.getLogger("nyx.rag")


class NyxRAGStore:
    """Ephemeral vector store for one game session."""

    def __init__(self, session_id: str | None = None) -> None:
        self._session_id = session_id or uuid.uuid4().hex[:12]
        self._client = chromadb.Client()  # in-memory, synchronous
        self._collection = self._client.create_collection(
            name=f"nyx_{self._session_id}",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"RAG store created: nyx_{self._session_id}")

    async def add_turn(
        self,
        turn_number: int,
        action: str,
        outcome: str,
        prose_summary: str,
        environment: str,
    ) -> None:
        """Embed a turn into the collection."""
        doc = (
            f"Turn {turn_number}: Action: {action} | "
            f"Outcome: {outcome} | "
            f"Environment: {environment} | "
            f"Summary: {prose_summary}"
        )
        doc_id = f"turn_{turn_number}"

        await asyncio.to_thread(
            self._collection.add,
            documents=[doc],
            ids=[doc_id],
            metadatas=[{
                "turn": turn_number,
                "outcome": outcome,
                "environment": environment,
            }],
        )
        logger.debug(f"RAG indexed turn {turn_number}")

    async def query(
        self, query_text: str, n_results: int = 5
    ) -> list[str]:
        """Semantic search for relevant past turns."""
        # Don't query empty collections
        count = await asyncio.to_thread(self._collection.count)
        if count == 0:
            return []

        n = min(n_results, count)
        results = await asyncio.to_thread(
            self._collection.query,
            query_texts=[query_text],
            n_results=n,
        )
        docs = results.get("documents", [[]])[0]
        logger.debug(f"RAG query returned {len(docs)} results")
        return docs

    def destroy(self) -> None:
        """Delete the collection. Called on game reset."""
        try:
            self._client.delete_collection(f"nyx_{self._session_id}")
            logger.info(f"RAG store destroyed: nyx_{self._session_id}")
        except Exception as e:
            logger.warning(f"RAG destroy failed: {e}")
