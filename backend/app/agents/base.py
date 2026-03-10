"""Base agent interface. All Children of Nyx implement this contract."""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel

from app.schemas.state import ThreadState


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
