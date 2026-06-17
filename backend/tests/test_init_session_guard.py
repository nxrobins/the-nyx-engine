"""POST /init must mark its new session in-flight during initialize() (THR-C6).

/action and /turn bracket their awaited kernel work in `with _in_flight(...)`
so eviction (idle TTL or over-cap LRU) skips the session. /init did not, so the
fresh session sat at processing==0 across initialize()'s many awaits — a
concurrent over-cap flood could LRU-evict it, call reset() on the kernel
initialize() was still mutating, and return a session_id that 404s on the
client's next request. This pins that init holds the in-flight guard.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.core.kernel import NyxKernel


def test_init_marks_session_in_flight_during_initialize(monkeypatch):
    observed: dict[str, int | None] = {}
    orig_init = NyxKernel.initialize

    async def spy(self, **kwargs):
        entry = next((e for e in routes._sessions.values() if e.kernel is self), None)
        # Captured WHILE initialize() runs — the in-flight guard must be held here.
        observed["processing"] = entry.processing if entry else None
        return await orig_init(self, **kwargs)

    monkeypatch.setattr(NyxKernel, "initialize", spy)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)

    resp = client.post("/api/init", json={
        "hamartia": "Unformed",
        "player_id": "init_guard",
        "name": "Orin",
        "gender": "boy",
        "first_memory": "A light in the distance I could not reach.",
    })

    assert resp.status_code == 200, resp.text
    assert observed["processing"] == 1   # in-flight during init (was 0 before the fix)
