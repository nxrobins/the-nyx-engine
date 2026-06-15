"""Black Forest Labs Flux — Milestone Image Generation.

When a soul vector hits 10, the kernel fires an image generation request
to BFL Flux. The result URL is sent to the frontend via SSE.

API flow:
  1. POST /v1/flux-pro-1.1 with prompt → returns task ID
  2. Poll GET /v1/get_result?id={id} until status == "Ready"
  3. Return the image URL from the result

All prompts are wrapped in the sumi-e aesthetic prefix.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("nyx.bfl")

_BFL_BASE_URL = "https://api.bfl.ai/v1"  # api.bfl.ml was retired
_POLL_INTERVAL = 1.0  # seconds
_POLL_TIMEOUT = 30.0  # seconds

# AT-E1: terminal non-Ready statuses — fail fast, never poll one to the timeout.
_TERMINAL_FAILURES = frozenset(
    {"Error", "Failed", "Content Moderated", "Request Moderated", "Task not found", "Expired"}
)


async def generate_image(
    prompt: str,
    api_key: str,
    model: str = "flux-pro-1.1",
    output_format: str | None = None,
    seed: int | None = None,
) -> str:
    """Generate an image via BFL Flux API.

    Args:
        prompt: Scene description (will be wrapped in sumi-e style).
        api_key: BFL API key.
        model: BFL model name.
        output_format: Optional "jpeg"/"png" — omitted when None (BFL's
            default; the Atelier passes "jpeg" for small, directly-promotable
            plates). BFL does not support webp.
        seed: Optional reproducibility seed — omitted when None (milestone
            images stay seedless so they vary; the Atelier passes a per-plate
            deterministic seed).

    Returns:
        Image URL string, or empty string on failure/timeout.
        The returned URL is a hosted, EXPIRING link — callers that keep
        the image must download the bytes immediately.
    """
    styled_prompt = f"{settings.bfl_style_prefix}, {prompt}, {settings.bfl_style_suffix}"

    payload: dict = {
        "prompt": styled_prompt,
        "width": 1024,
        "height": 768,
    }
    if output_format:
        payload["output_format"] = output_format
    if seed is not None:  # AT-E5: None → omitted, so the milestone path is unchanged
        payload["seed"] = seed

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Submit generation request
        try:
            submit_resp = await client.post(
                f"{_BFL_BASE_URL}/{model}",
                headers={"x-key": api_key},
                json=payload,
            )
            submit_resp.raise_for_status()
            submit_data = submit_resp.json()
            task_id = submit_data.get("id")
            polling_url = submit_data.get("polling_url")  # modern API returns a region-routed URL
            if not task_id:
                logger.error("BFL: No task ID in response")
                return ""
        except Exception as e:
            logger.error(f"BFL submit failed: {e}")
            return ""

        # Step 2: Poll for result
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            try:
                poll_resp = await client.get(
                    polling_url or f"{_BFL_BASE_URL}/get_result",
                    params=None if polling_url else {"id": task_id},
                    headers={"x-key": api_key},
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()

                status = data.get("status")
                if status == "Ready":
                    url = data.get("result", {}).get("sample", "")
                    logger.info(f"BFL image ready: {url[:80]}...")
                    return url
                elif status in _TERMINAL_FAILURES:
                    logger.error(f"BFL terminal status {status!r}: {data}")
                    return ""
                # Otherwise keep polling ("Pending", "Processing")
            except httpx.HTTPStatusError as e:
                # A permanent client error (bad/expired key authorizing POST but
                # not GET, or a vanished task) will NEVER resolve — fail fast
                # instead of looping once/sec to the 30s timeout (audit M2).
                # 429 (rate-limit) and 5xx are transient: keep polling those.
                code = e.response.status_code
                if 400 <= code < 500 and code != 429:
                    logger.error(f"BFL poll: permanent HTTP {code}, abandoning: {e}")
                    return ""
                logger.warning(f"BFL poll: transient HTTP {code}, retrying: {e}")
            except Exception as e:
                logger.warning(f"BFL poll error: {e}")

        logger.warning(f"BFL timed out after {_POLL_TIMEOUT}s")
        return ""
