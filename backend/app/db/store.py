"""Store interfaces for durable thread persistence."""

from __future__ import annotations

from typing import Protocol


class ThreadStore(Protocol):
    """Persistence backend contract used by the kernel and API."""

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def ensure_player(self, player_id: str) -> None: ...
    async def create_thread(self, player_id: str, hamartia: str) -> int | None: ...
    async def update_thread_death(
        self,
        thread_id: int | None,
        epitaph: str,
        final_turn: int,
        *,
        death_reason: str = "",
        final_soul_vectors: dict | None = None,
    ) -> None: ...
    async def create_turn(
        self,
        thread_id: int | None,
        turn_number: int,
        action: str,
        outcome: str,
        prose_summary: str,
        soul_vectors: dict,
    ) -> None: ...
    async def append_chronicle(self, thread_id: int | None, sentence: str) -> None: ...
    async def append_factual_chronicle(self, thread_id: int | None, digest: str) -> None: ...
    async def get_dead_threads(self, player_id: str) -> list[dict]: ...
    async def get_last_ancestor(self, player_id: str) -> dict | None: ...

    # Durability (THE THREAD PERSISTS) — one latest-wins snapshot per resume
    # token; the store enforces the monotonic guard (SC-3/CF-2).
    async def save_snapshot(
        self,
        token: str,
        player_id: str,
        thread_id: int | None,
        turn_count: int,
        schema_version: int,
        state_json: str,
        chapters_json: str,
    ) -> None: ...
    async def load_snapshot(self, token: str) -> dict | None: ...
