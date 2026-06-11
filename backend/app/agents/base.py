"""Base agent interface. All Children of Nyx implement this contract."""

from __future__ import annotations

import abc
import asyncio
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.schemas.state import ThreadState


async def mock_pause(seconds: float) -> None:
    """Simulated mock-mode latency, scaled by settings.

    Production mock mode keeps the pacing feel; tests set
    mock_latency_scale=0 so the suite runs at full speed.
    """
    scaled = seconds * settings.mock_latency_scale
    if scaled > 0:
        await asyncio.sleep(scaled)


class AgentBase(abc.ABC):
    """Every agent receives the thread state and player action,
    returns a typed Pydantic response."""

    name: str = "unnamed"

    @abc.abstractmethod
    async def evaluate(
        self, state: ThreadState, action: str
    ) -> BaseModel:
        """Process the current state and return agent-specific response."""
        ...
