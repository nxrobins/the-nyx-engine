"""Unified LLM abstraction via LiteLLM v2.0.

Replaces the 285-line multi-provider implementation with a single
routing layer. LiteLLM handles provider dispatch, API formatting,
and error normalization.

Model string format: "provider/model" e.g.:
  - "anthropic/claude-sonnet-4-20250514"
  - "openai/mercury-2"  (with custom api_base for Mercury)
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator

import litellm

from app.core.config import settings

logger = logging.getLogger("nyx.llm")

# ---------------------------------------------------------------------------
# LiteLLM environment configuration
# Mercury (Inception Labs) uses OpenAI-compatible API at a custom base URL.
# LiteLLM reads MERCURY_API_BASE from env to route "openai/mercury-2".
# ---------------------------------------------------------------------------

def _configure_litellm() -> None:
    """Set up LiteLLM environment variables for provider routing."""
    # Anthropic
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    # Mercury via OpenAI-compatible endpoint
    if settings.mercury_api_key:
        os.environ["OPENAI_API_KEY"] = settings.mercury_api_key
        os.environ["OPENAI_API_BASE"] = settings.mercury_api_base

    # Suppress LiteLLM's verbose logging
    litellm.set_verbose = False


_configure_litellm()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.8,
    max_tokens: int = 1024,
    json_mode: bool = False,
) -> str:
    """Generate a completion via LiteLLM.

    Args:
        model: LiteLLM model string, e.g. "anthropic/claude-sonnet-4-20250514"
        json_mode: Hint to provider that response should be valid JSON.
    """
    kwargs: dict = dict(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug(f"LLM call: model={model}, temp={temperature}")
    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content or ""
    logger.debug(f"LLM response: {len(content)} chars")
    return content


async def stream(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.8,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """Stream a completion token-by-token via LiteLLM."""
    response = await litellm.acompletion(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
