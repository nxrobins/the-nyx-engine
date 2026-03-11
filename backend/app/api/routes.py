"""API routes for the Nyx Engine v3.0.

POST /init    - Initialize session with hamartia choice (Turn 0)
POST /action  - Submit a player action, get full turn result
POST /turn    - SSE stream: 3-Phase pipeline (mechanic → prose → state)
GET  /stream  - SSE with Hypnos mask + BFL heartbeat (legacy)
GET  /state   - Current thread state (debug)
POST /reset   - Reset the game session

v3.0: Session isolation via SessionManager (keyed by UUID).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.db import get_dead_threads
from app.schemas.state import InitRequest, PlayerAction, TurnResult
from app.services.bfl import generate_image

logger = logging.getLogger("nyx.api")

router = APIRouter()


# ---------------------------------------------------------------------------
# Session Manager — isolates concurrent players
# ---------------------------------------------------------------------------

_SESSION_TTL = 3600  # 1 hour — evict idle sessions


class _SessionEntry:
    __slots__ = ("kernel", "last_active")

    def __init__(self, kernel: NyxKernel) -> None:
        self.kernel = kernel
        self.last_active = time.monotonic()

    def touch(self) -> None:
        self.last_active = time.monotonic()


_sessions: dict[str, _SessionEntry] = {}


def _get_or_create_session(session_id: str | None = None) -> tuple[str, NyxKernel]:
    """Return (session_id, kernel). Creates a new session if id is missing/expired."""
    _evict_stale()

    if session_id and session_id in _sessions:
        entry = _sessions[session_id]
        entry.touch()
        return session_id, entry.kernel

    # New session
    sid = uuid.uuid4().hex
    entry = _SessionEntry(NyxKernel())
    _sessions[sid] = entry
    logger.info(f"Session created: {sid} (active={len(_sessions)})")
    return sid, entry.kernel


def _require_session(session_id: str) -> NyxKernel:
    """Lookup an existing session or 404."""
    _evict_stale()

    entry = _sessions.get(session_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    entry.touch()
    return entry.kernel


def _destroy_session(session_id: str) -> None:
    """Destroy a session and free its kernel."""
    entry = _sessions.pop(session_id, None)
    if entry:
        entry.kernel.reset()
        logger.info(f"Session destroyed: {session_id} (remaining={len(_sessions)})")


def _evict_stale() -> None:
    """Remove sessions idle longer than _SESSION_TTL."""
    now = time.monotonic()
    stale = [sid for sid, e in _sessions.items() if now - e.last_active > _SESSION_TTL]
    for sid in stale:
        entry = _sessions.pop(sid, None)
        if entry:
            try:
                entry.kernel.reset()
            except Exception:
                pass
            logger.info(f"Session evicted (idle): {sid}")


# ------------------------------------------------------------------
# POST /init — Turn 0: Choose hamartia, generate prophecy
# ------------------------------------------------------------------

@router.post("/init", response_model=TurnResult)
async def init_session(req: InitRequest) -> TurnResult:
    """Initialize a new game session with a chosen hamartia.

    Always creates a fresh session. Returns the session_id
    that the client must send back on every subsequent request.
    """
    sid, kernel = _get_or_create_session()
    result = await kernel.initialize(
        hamartia=req.hamartia,
        player_id=req.player_id,
        name=req.name,
        gender=req.gender,
        first_memory=req.first_memory,
    )
    # model_copy ensures session_id is in model_fields_set for serialization
    return result.model_copy(update={"session_id": sid})


# ------------------------------------------------------------------
# POST /action — Synchronous turn processing
# ------------------------------------------------------------------

@router.post("/action", response_model=TurnResult)
async def submit_action(action: PlayerAction) -> TurnResult:
    """Synchronous turn processing. Returns the full result after all
    agents resolve. Use /turn for the streaming experience."""
    kernel = _require_session(action.session_id)
    result = await kernel.process_turn(action.action)
    return result.model_copy(update={"session_id": action.session_id})


# ------------------------------------------------------------------
# POST /turn — Streaming SSE (Sprint 6: 3-Phase Pipeline)
# ------------------------------------------------------------------

@router.post("/turn")
async def stream_turn_post(action: PlayerAction, request: Request):
    """3-Phase streaming turn pipeline.

    Phase 1: mechanic — Lachesis math + conflict resolution (immediate)
    Phase 2: prose    — Clotho tokens streamed for typewriter effect
    Phase 3: state    — Final state + choices + cleanup

    BFL image generation runs post-stream if a milestone is triggered.
    """
    kernel = _require_session(action.session_id)

    async def event_generator():
        # Stream the 3-phase kernel pipeline
        async for chunk in kernel.process_turn_stream(action.action):
            if await request.is_disconnected():
                logger.info("Client disconnected during stream")
                return
            yield chunk

        # BFL image: fire after stream if milestone triggered
        if (
            kernel.state.the_loom.milestone_reached
            and kernel.state.the_loom.image_prompt_trigger
            and settings.bfl_api_key
        ):
            try:
                image_url = await generate_image(
                    prompt=kernel.state.the_loom.image_prompt_trigger,
                    api_key=settings.bfl_api_key,
                )
                if image_url:
                    yield "data: " + json.dumps({
                        "type": "image",
                        "url": image_url,
                    }) + "\n\n"
            except Exception as e:
                logger.warning(f"BFL image generation failed: {e}")

        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# GET /state — Debug endpoint
# ------------------------------------------------------------------

@router.get("/state")
async def get_state(session_id: str = ""):
    """Debug endpoint: current thread state."""
    if not session_id:
        return {"error": "session_id required"}
    kernel = _require_session(session_id)
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
async def reset_session(action: PlayerAction | None = None):
    """Reset the game to a fresh state. Destroys the session."""
    session_id = action.session_id if action else ""
    if session_id and session_id in _sessions:
        _destroy_session(session_id)
    return {"status": "reset", "message": "A new thread begins."}
