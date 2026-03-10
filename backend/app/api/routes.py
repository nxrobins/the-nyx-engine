"""API routes for the Nyx Engine v2.0.

POST /init    - Initialize session with hamartia choice (Turn 0)
POST /action  - Submit a player action, get full turn result
GET  /stream  - SSE stream: Hypnos filler + final Clotho prose + BFL image
GET  /state   - Current thread state (debug)
POST /reset   - Reset the game session
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.db import get_dead_threads
from app.schemas.state import InitRequest, PlayerAction, TurnResult
from app.services.bfl import generate_image

logger = logging.getLogger("nyx.api")

router = APIRouter()

# In-memory kernel instance (future: session-based instances)
_kernel = NyxKernel()


def _get_kernel() -> NyxKernel:
    return _kernel


# ------------------------------------------------------------------
# POST /init — Turn 0: Choose hamartia, generate prophecy
# ------------------------------------------------------------------

@router.post("/init", response_model=TurnResult)
async def init_session(req: InitRequest) -> TurnResult:
    """Initialize a new game session with a chosen hamartia.

    Returns the Turn 0 result with the initial prophecy.
    """
    global _kernel
    _kernel = NyxKernel()
    kernel = _get_kernel()
    result = await kernel.initialize(
        hamartia=req.hamartia,
        player_id=req.player_id,
        name=req.name,
        gender=req.gender,
        first_memory=req.first_memory,
    )
    return result


# ------------------------------------------------------------------
# POST /action — Synchronous turn processing
# ------------------------------------------------------------------

@router.post("/action", response_model=TurnResult)
async def submit_action(action: PlayerAction) -> TurnResult:
    """Synchronous turn processing. Returns the full result after all
    agents resolve. Use /stream for the Hypnos-masked experience."""
    kernel = _get_kernel()
    result = await kernel.process_turn(action.action)
    return result


# ------------------------------------------------------------------
# GET /stream — SSE with Hypnos mask + BFL heartbeat
# ------------------------------------------------------------------

@router.get("/stream")
async def stream_turn(action: str, request: Request):
    """SSE endpoint implementing the Hypnos Mask protocol.

    1. Immediately streams Hypnos filler fragments (type: 'hypnos')
    2. Concurrently processes the real turn through the Kernel
    3. Sends the final result (type: 'result') which overwrites the filler
    4. If milestone triggered, holds connection open with heartbeats
       while BFL generates the image
    5. Sends 'image' event with URL when BFL completes
    6. Sends 'done' event to signal completion
    """
    kernel = _get_kernel()

    async def event_generator():
        # Launch the heavy backend processing
        turn_task = asyncio.create_task(kernel.process_turn(action))

        # Stream Hypnos filler while we wait
        async for fragment in kernel.get_hypnos_stream(action):
            if await request.is_disconnected():
                turn_task.cancel()
                return
            yield {
                "event": "hypnos",
                "data": json.dumps({"text": fragment}),
            }

        # Wait for the real result
        result = await turn_task

        # Send the final prose (overwrites Hypnos on frontend)
        yield {
            "event": "result",
            "data": result.model_dump_json(),
        }

        # ----------------------------------------------------------
        # BFL Image: If milestone triggered, hold SSE open with
        # heartbeat pings while we poll the image API.
        #
        # GOTCHA: The SSE generator closes when it stops yielding.
        # Clotho finishes in ~3-4s, but BFL takes 5-8s. Without
        # heartbeats, the connection severs before the image URL
        # is ready.
        # ----------------------------------------------------------
        if (
            result.state.the_loom.milestone_reached
            and result.state.the_loom.image_prompt_trigger
            and settings.bfl_api_key
        ):
            bfl_task = asyncio.create_task(
                generate_image(
                    prompt=result.state.the_loom.image_prompt_trigger,
                    api_key=settings.bfl_api_key,
                )
            )
            # Send heartbeats while waiting for BFL
            while not bfl_task.done():
                if await request.is_disconnected():
                    bfl_task.cancel()
                    return
                yield {"event": "heartbeat", "data": ""}
                await asyncio.sleep(1)

            try:
                image_url = bfl_task.result()
                if image_url:
                    yield {
                        "event": "image",
                        "data": json.dumps({"url": image_url}),
                    }
            except Exception as e:
                logger.warning(f"BFL image generation failed: {e}")

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ------------------------------------------------------------------
# GET /state — Debug endpoint
# ------------------------------------------------------------------

@router.get("/state")
async def get_state():
    """Debug endpoint: current thread state."""
    kernel = _get_kernel()
    return kernel.state.model_dump()


# ------------------------------------------------------------------
# GET /hamartia-options — List available tragic flaws
# ------------------------------------------------------------------

@router.get("/hamartia-options")
async def get_hamartia_options():
    """Return the list of available hamartia choices."""
    return {"options": settings.hamartia_options}


# ------------------------------------------------------------------
# GET /threads/{player_id} — Past lives for title screen
# ------------------------------------------------------------------

@router.get("/threads/{player_id}")
async def get_player_threads(player_id: str):
    """Return all dead threads for a player (past lives)."""
    threads = await get_dead_threads(player_id)
    return {"threads": threads}


# ------------------------------------------------------------------
# POST /reset — Reset game session
# ------------------------------------------------------------------

@router.post("/reset")
async def reset_session():
    """Reset the game to a fresh state. Destroys ChromaDB session."""
    global _kernel
    kernel = _get_kernel()
    kernel.reset()
    _kernel = NyxKernel()
    return {"status": "reset", "message": "A new thread begins."}
