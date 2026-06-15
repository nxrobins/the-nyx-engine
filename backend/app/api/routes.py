"""API routes for the Nyx Engine v3.0.

POST /init    - Initialize session with hamartia choice (Turn 0)
POST /action  - Submit a player action, get full turn result
POST /turn    - SSE stream: 3-Phase pipeline (mechanic → prose → state)
GET  /safety  - The Vigil: care-gate state + server-owned crisis copy
GET  /state   - Current thread state (debug)
GET  /hamartia-options - List available tragic flaws
GET  /threads/{player_id} - Past lives for the title screen
GET  /library, /library/{book_id} - The bound lives (Scribe P3)
GET  /assays  - Per-world fitness from finished lives (Assayer P4)
GET  /plates/{world_id}[/{filename}] - Curated world art (The Ink)
POST /reset   - Reset the game session

v3.0: Session isolation via SessionManager (keyed by UUID).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.core.config import settings
from app.core.kernel import NyxKernel
from app.db import get_dead_threads
from app.schemas.state import InitRequest, PlayerAction, TurnResult
from app.services.bfl import generate_image
from app.services.legacy import augment_thread_summary
from app.services.welfare import CRISIS_RESOURCES, detect_crisis

logger = logging.getLogger("nyx.api")

router = APIRouter()


# ---------------------------------------------------------------------------
# Session Manager — isolates concurrent players
# ---------------------------------------------------------------------------

_SESSION_TTL = 3600  # 1 hour — evict idle sessions


class _SessionEntry:
    __slots__ = ("kernel", "last_active", "processing")

    def __init__(self, kernel: NyxKernel) -> None:
        self.kernel = kernel
        self.last_active = time.monotonic()
        self.processing = 0   # in-flight turn refcount — never evicted while > 0 (THR-C6)

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
    _evict_lru_if_over_cap(keep_sid=sid)
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
    """Remove sessions idle longer than _SESSION_TTL. Never an in-flight turn
    (THR-C6: last_active is set once at request entry and not refreshed during a
    multi-minute turn, so a busy session can look 'stale' — the refcount guards it)."""
    now = time.monotonic()
    stale = [
        sid for sid, e in _sessions.items()
        if now - e.last_active > _SESSION_TTL and e.processing == 0
    ]
    for sid in stale:
        entry = _sessions.pop(sid, None)
        if entry:
            try:
                entry.kernel.reset()
            except Exception:
                pass
            logger.info(f"Session evicted (idle): {sid}")


def _evict_lru_if_over_cap(keep_sid: str | None = None) -> None:
    """THR-C6: keep the live-session count under the cap by dropping the least-
    recently-active IDLE session. NEVER evicts an in-flight turn (processing > 0)
    NOR the session just created (keep_sid); if the only candidate left is busy or
    the new session (a degenerate all-busy flood), it logs and serves anyway — the
    always-continue invariant wins, and THR-C5's budget still bounds LLM fan-out."""
    cap = settings.session_count_cap
    while len(_sessions) > cap:
        idle = sorted(
            (e.last_active, sid) for sid, e in _sessions.items()
            if e.processing == 0 and sid != keep_sid
        )
        if not idle:
            logger.warning(
                f"Session cap {cap} exceeded but no idle evictable session; serving anyway"
            )
            return
        sid = idle[0][1]
        entry = _sessions.pop(sid, None)
        if entry:
            try:
                entry.kernel.reset()
            except Exception:
                pass
            logger.info(f"Session evicted (LRU over cap): {sid}")


@contextmanager
def _in_flight(session_id: str):
    """Mark a session as actively processing a turn so eviction skips it (THR-C6).
    Sync CM — it brackets the awaited kernel work without becoming part of it."""
    entry = _sessions.get(session_id)
    if entry is not None:
        entry.processing += 1
    try:
        yield
    finally:
        if entry is not None:
            entry.processing = max(0, entry.processing - 1)


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
    # The Vigil: decide the care payload BEFORE the kernel runs (SAFE-C6), so the
    # death-result model_copy below carries it. Detection runs regardless of the
    # gate (SAFE-C2); only the displayed copy is gated (welfare_copy_reviewed).
    update: dict = {"session_id": action.session_id}
    if detect_crisis(action.action).flagged and settings.welfare_copy_reviewed:
        update["crisis_resources"] = CRISIS_RESOURCES
    with _in_flight(action.session_id):   # THR-C6: not evictable mid-turn
        result = await kernel.process_turn(action.action)
    return result.model_copy(update=update)


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
    # The Vigil: decide the care frame BEFORE the stream loop (SAFE-C6). Detection
    # runs regardless of the gate (SAFE-C2); only the emitted frame is gated.
    crisis_flagged = detect_crisis(action.action).flagged

    async def event_generator():
        # SAFE-C6/C9: the crisis frame is stream position 0 — yielded before the
        # kernel runs, so a mid-stream exception or an early death-return cannot
        # suppress it, and the client opens the interstitial above the death.
        if crisis_flagged and settings.welfare_copy_reviewed:
            yield "data: " + json.dumps({
                "type": "crisis_resources",
                "payload": CRISIS_RESOURCES,
            }) + "\n\n"

        # Stream the 3-phase kernel pipeline (in-flight for THR-C6 — the long
        # part of the turn; eviction skips this session while it runs).
        with _in_flight(action.session_id):
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
# GET /safety — The Vigil: gate state + server-owned crisis copy
# ------------------------------------------------------------------

@router.get("/safety")
async def get_safety():
    """Tell the client whether the duty-of-care surface is active and hand it
    the server-owned crisis copy. 100% static — echoes nothing the player typed.

    `resources` is `None` until a human reviews the words + detection and flips
    `welfare_copy_reviewed` (SAFE-C5 gate). The client's hardcoded always-on help
    link (SAFE-C3/C8) never depends on this call — this only ENRICHES the in-flow
    interstitial and decides whether to arm the consent gate.
    """
    reviewed = settings.welfare_copy_reviewed
    return {
        "reviewed": reviewed,
        "resources": CRISIS_RESOURCES if reviewed else None,
    }


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
    return {"threads": [augment_thread_summary(thread) for thread in threads]}


# ------------------------------------------------------------------
# GET /library — The Tapestry as a shelf (Scribe P3)
# ------------------------------------------------------------------

@router.get("/library")
async def get_library():
    """All bound lives: manifests for the title-screen shelf."""
    from app.services.bookbinder import list_books

    return {
        "books": [
            {
                "book_id": b.book_id,
                "title": b.title,
                "player_name": b.player_name,
                "hamartia": b.hamartia,
                "settlement": b.settlement,
                "epitaph": b.epitaph,
                "died_turn": b.died_turn,
                "chapter_count": len(b.chapters),
            }
            for b in list_books()
        ]
    }


@router.get("/library/{book_id}")
async def get_book(book_id: str):
    """One bound life, as markdown. 404 if the shelf has no such spine."""
    from app.services.bookbinder import load_book_markdown

    markdown = load_book_markdown(book_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail="No such book in the Tapestry.")
    return {"book_id": book_id, "markdown": markdown}


# ------------------------------------------------------------------
# GET /plates — The Atelier's curated canon images (The Ink, Layer 1)
# ------------------------------------------------------------------

@router.get("/plates/{world_id}")
async def get_plate_manifest(world_id: str):
    """A world's plate manifest. Always 200; empty when no art exists.

    no-store: the manifest re-scans the art dir every request, so a
    curation change is visible immediately (the no-cached-listing law).
    """
    from app.services.plates import plate_manifest

    return JSONResponse(
        plate_manifest(world_id),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/plates/{world_id}/{filename}")
async def get_plate(world_id: str, filename: str):
    """One plate, re-gated at serve time (INK-E3): filename law, size law,
    realpath containment. 404 outside the law; 413 over the 512 KB cap."""
    from app.services.plates import resolve_plate

    path, media, status = resolve_plate(world_id, filename)
    if status == 413:
        raise HTTPException(status_code=413, detail="Plate exceeds the 512 KB law.")
    if path is None:
        raise HTTPException(status_code=404, detail="No such plate.")
    return FileResponse(
        path,
        media_type=media,
        headers={"Cache-Control": "public, max-age=300"},
    )


# ------------------------------------------------------------------
# GET /assays — The Assayer's report (Morpheus P4)
# ------------------------------------------------------------------

@router.get("/assays")
async def get_assays(world_id: str = ""):
    """Per-world fitness from finished lives, plus the raw verdicts."""
    from app.services.assayer import list_verdicts, world_fitness

    return {
        "fitness": world_fitness(world_id or None),
        "verdicts": [v.model_dump() for v in list_verdicts()][-100:],
    }


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
