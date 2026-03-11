"""Unified LLM abstraction via LiteLLM v2.0.

Replaces the 285-line multi-provider implementation with a single
routing layer. LiteLLM handles provider dispatch, API formatting,
and error normalization.

Model string format: "provider/model" e.g.:
  - "anthropic/claude-sonnet-4-20250514"
  - "openai/mercury-2"  (with custom api_base for Mercury)

v2.1: Per-call credential injection replaces global env mutation.
      Fixes P1-004 — Mercury credentials no longer clobber OPENAI_API_KEY.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import litellm

from app.core.config import settings

logger = logging.getLogger("nyx.llm")

# Suppress LiteLLM's verbose logging
litellm.set_verbose = False


# ---------------------------------------------------------------------------
# Credential resolver — per-call, no global env mutation
# ---------------------------------------------------------------------------

def _resolve_credentials(model: str) -> dict:
    """Return provider-specific kwargs for a LiteLLM call.

    Instead of writing API keys into os.environ (which causes credential
    collision between providers), we inject them per-call via kwargs.
    """
    kwargs: dict = {}

    if model.startswith("anthropic/"):
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key

    elif model.startswith("openai/"):
        # Mercury routes through OpenAI-compatible endpoint
        if settings.mercury_api_key:
            kwargs["api_key"] = settings.mercury_api_key
        if settings.mercury_api_base:
            kwargs["api_base"] = settings.mercury_api_base

    return kwargs


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
        **_resolve_credentials(model),
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
        **_resolve_credentials(model),
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
