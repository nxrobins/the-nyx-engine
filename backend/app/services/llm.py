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

import asyncio
import logging
from typing import AsyncGenerator

import litellm

from app.core.config import settings

logger = logging.getLogger("nyx.llm")

# Suppress LiteLLM's verbose logging
litellm.set_verbose = False


# ---------------------------------------------------------------------------
# The Throttle — a global concurrency budget on REAL-model calls (THR-C5)
# ---------------------------------------------------------------------------
#
# NEVER reached in mock mode: every agent returns at its `model == "mock"` guard
# before calling generate()/stream(), so the semaphore and the timeout/retry
# kwargs are provably inert under the hermetic suite.
#
# The semaphore wraps ONLY the leaf acompletion — it is never held by the kernel
# across its per-turn asyncio.gather, so a budget smaller than the fan-out
# serializes (slower) but never deadlocks. Acquisition is bounded: if no slot
# frees within llm_acquire_timeout the call raises, and the agent degrades to
# mock via its normal except path (counted by _degrade) — it never blocks a turn.
#
# Lazily created so it binds to the running event loop at first real use (mock
# tests never create it); the conftest autouse fixture resets it to None per-test
# so a loop-bound semaphore can't leak across pytest-asyncio's per-test loops.

_BUDGET: asyncio.Semaphore | None = None


def _get_budget() -> asyncio.Semaphore:
    global _BUDGET
    if _BUDGET is None:
        _BUDGET = asyncio.Semaphore(settings.llm_concurrency_budget)
    return _BUDGET


async def _acquire_budget() -> asyncio.Semaphore:
    """Acquire a real-model concurrency slot, bounded. Raises TimeoutError on
    exhaustion so the caller degrades to mock rather than blocking (THR-C5)."""
    sem = _get_budget()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=settings.llm_acquire_timeout)
    except asyncio.TimeoutError as exc:
        raise TimeoutError("llm concurrency budget exhausted") from exc
    return sem


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
    # THR-C3/C4: bound each real call. `timeout=` (NOT request_timeout=, which is
    # a litellm module-global, inert as a call kwarg) + a single internal retry.
    kwargs["timeout"] = settings.llm_request_timeout
    kwargs["num_retries"] = settings.llm_num_retries

    logger.debug(f"LLM call: model={model}, temp={temperature}")
    sem = await _acquire_budget()
    try:
        response = await litellm.acompletion(**kwargs)
    finally:
        sem.release()
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
    # THR-C5: hold one budget slot for the whole stream — the stream IS the
    # in-flight call — and release it only once the generator is exhausted/closed.
    sem = await _acquire_budget()
    try:
        response = await litellm.acompletion(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=settings.llm_request_timeout,   # THR-C3/C4
            num_retries=settings.llm_num_retries,
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
    finally:
        sem.release()
