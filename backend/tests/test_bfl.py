"""BFL poll-loop fail-fast on permanent HTTP errors (audit M2).

generate_image's poll loop swallowed EVERY poll exception and retried to the 30s
timeout, so a bad/expired key — or any permanent 4xx — burned the full window per
milestone image and per Atelier plate. A permanent client error now abandons
immediately; transient errors (429, 5xx) still retry. bfl.py had no test before.
"""

from __future__ import annotations

import httpx

import app.services.bfl as bfl


def _factory_with(transport: httpx.MockTransport):
    """An httpx.AsyncClient factory that injects a mock transport (capturing the
    real class BEFORE the monkeypatch swaps it out)."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    return factory


async def test_poll_fails_fast_on_permanent_http_error(monkeypatch):
    calls = {"get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"id": "t1", "polling_url": "https://api.bfl.ai/v1/get_result?id=t1"}
            )
        calls["get"] += 1
        return httpx.Response(403, json={"error": "forbidden"})  # permanent

    monkeypatch.setattr(bfl.httpx, "AsyncClient", _factory_with(httpx.MockTransport(handler)))
    monkeypatch.setattr(bfl, "_POLL_INTERVAL", 0.0)

    url = await bfl.generate_image("a quiet harbor", api_key="bad-key")
    assert url == ""
    assert calls["get"] == 1  # abandoned after one poll, not polled to timeout


async def test_poll_retries_transient_then_succeeds(monkeypatch):
    calls = {"get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"id": "t2", "polling_url": "https://api.bfl.ai/v1/get_result?id=t2"}
            )
        calls["get"] += 1
        if calls["get"] == 1:
            return httpx.Response(503, json={"error": "busy"})  # transient — keep polling
        return httpx.Response(200, json={"status": "Ready", "result": {"sample": "https://img/x.jpg"}})

    monkeypatch.setattr(bfl.httpx, "AsyncClient", _factory_with(httpx.MockTransport(handler)))
    monkeypatch.setattr(bfl, "_POLL_INTERVAL", 0.0)

    url = await bfl.generate_image("a quiet harbor", api_key="ok-key")
    assert url == "https://img/x.jpg"
    assert calls["get"] == 2  # retried the transient 503, then got Ready
