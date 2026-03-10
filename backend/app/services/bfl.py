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

logger = logging.getLogger("nyx.bfl")

_BFL_BASE_URL = "https://api.bfl.ml/v1"
_STYLE_PREFIX = "Monochrome sumi-e ink wash"
_STYLE_SUFFIX = "black ink on aged parchment, no text, no UI elements"
_POLL_INTERVAL = 1.0  # seconds
_POLL_TIMEOUT = 30.0  # seconds


async def generate_image(
    prompt: str,
    api_key: str,
    model: str = "flux-pro-1.1",
) -> str:
    """Generate an image via BFL Flux API.

    Args:
        prompt: Scene description (will be wrapped in sumi-e style).
        api_key: BFL API key.
        model: BFL model name.

    Returns:
        Image URL string, or empty string on failure/timeout.
    """
    styled_prompt = f"{_STYLE_PREFIX}, {prompt}, {_STYLE_SUFFIX}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Submit generation request
        try:
            submit_resp = await client.post(
                f"{_BFL_BASE_URL}/{model}",
                headers={"x-key": api_key},
                json={
                    "prompt": styled_prompt,
                    "width": 1024,
                    "height": 768,
                },
            )
            submit_resp.raise_for_status()
            task_id = submit_resp.json().get("id")
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
                    f"{_BFL_BASE_URL}/get_result",
                    params={"id": task_id},
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()

                status = data.get("status")
                if status == "Ready":
                    url = data.get("result", {}).get("sample", "")
                    logger.info(f"BFL image ready: {url[:80]}...")
                    return url
                elif status in ("Error", "Failed"):
                    logger.error(f"BFL generation failed: {data}")
                    return ""
                # Otherwise keep polling ("Pending", "Processing")
            except Exception as e:
                logger.warning(f"BFL poll error: {e}")

        logger.warning(f"BFL timed out after {_POLL_TIMEOUT}s")
        return ""
