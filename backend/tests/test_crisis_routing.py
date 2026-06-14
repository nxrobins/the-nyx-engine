"""The Vigil — Crisis-Routing (Player Safety, Phase 2).

The duty-of-care surface: a person who types genuine ideation is shown real,
independent crisis resources while the in-fiction death resolves untouched.

The load-bearing invariant is SAFE-C1/C7: there is exactly ONE canonical flagged
set (`welfare.is_flagged` / `detect_crisis`) and it drives BOTH the care channel
AND the kernel's durable-store redaction. They therefore cannot desync into a
leak (a disclosure that shows the card but escapes redaction) or a zero-recall
hole (a disclosure that is redacted but never offered help). These tests pin that
one set at every layer:

  * the detector unit, on a REAL ideation corpus distinct from the death phrases
    (SAFE-C4 — recall is asserted, not inferred from the subset relation);
  * the superset relation REAL_WORLD_ATROPOS_PHRASES ⊆ atropos_death_keywords,
    merge-blocking, so a new real-world death phrase can't skip care (SAFE-C7);
  * the route gate — detection/redaction never gated, only the rendered copy is
    (SAFE-C2/C5), exercised with `welfare_copy_reviewed` both False and True;
  * a no-leak parity sweep over the ideation corpus through the live kernel,
    proving the unified set reaches zero persistence sites even gate-OFF.

Hermetic: the autouse conftest fixture forces mock mode + zero latency; the
route tests build a minimal FastAPI app + TestClient (never importing main.py,
whose lifespan would open the DB pool) — mirroring test_plates.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.core.config import settings
from app.services.welfare import (
    CRISIS_RESOURCES,
    REAL_WORLD_ATROPOS_PHRASES,
    REDACTION_TOKEN,
    detect_crisis,
)

# A positive corpus of GENUINE ideation phrasings, deliberately DISJOINT from the
# real-world death-trigger phrases — so a green build requires real recall, not
# just the subset relation (SAFE-C4). These must all flag.
IDEATION_CORPUS = (
    "I want to kill myself",
    "i'm going to end my life",
    "I want to die",
    "I want to hurt myself",
    "i can't go on anymore",
    "I don't want to be here anymore",
    "i feel so suicidal",
)


# ---------------------------------------------------------------------------
# The one canonical detector (SAFE-C4 recall + privacy of the signal)
# ---------------------------------------------------------------------------

class TestDetectCrisis:
    @pytest.mark.parametrize("phrase", IDEATION_CORPUS)
    def test_genuine_ideation_flags(self, phrase):
        sig = detect_crisis(phrase)
        assert sig.flagged is True
        assert sig.pattern_class in ("ideation", "self_destruct")

    @pytest.mark.parametrize("phrase", REAL_WORLD_ATROPOS_PHRASES)
    def test_every_real_world_death_phrase_flags(self, phrase):
        assert detect_crisis(f"I {phrase} now").flagged is True

    @pytest.mark.parametrize(
        "phrase",
        ["attack the guard", "help Sera with the harvest",
         "I embrace the void", "I welcome oblivion", "walk to the market"],
    )
    def test_ordinary_and_poetic_not_flagged(self, phrase):
        # Poetic game vocab ends the thread in the fiction but is NOT a real-world
        # disclosure — the discriminator is the real-world referent.
        assert detect_crisis(phrase).flagged is False

    def test_signal_never_carries_the_typed_text(self):
        # Privacy: the object exposes only a bool + coarse class, never the match.
        dumped = detect_crisis("I want to kill myself and nobody knows").model_dump()
        assert set(dumped) == {"flagged", "pattern_class"}
        assert "nobody" not in json.dumps(dumped).lower()

    def test_canonicalization_defeats_whitespace_evasion(self):
        assert detect_crisis("I   want   to    KILL   MYSELF").flagged is True

    def test_empty_action_is_not_flagged(self):
        assert detect_crisis("").flagged is False

    def test_fails_SAFE_on_internal_error(self, monkeypatch):
        # On ANY internal error, fail FLAGGED (show help + redact) — never
        # silently 'not flagged' (the unifying law: more help, less leak).
        import app.services.welfare as w

        def boom(_):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(w, "_canonical", boom)
        assert w.detect_crisis("anything at all").flagged is True


# ---------------------------------------------------------------------------
# The superset invariant — merge-blocking (SAFE-C7 / the matrix)
# ---------------------------------------------------------------------------

class TestSupersetInvariant:
    def test_real_world_phrases_are_subset_of_death_keywords(self):
        keywords = {k.lower() for k in settings.atropos_death_keywords}
        for phrase in REAL_WORLD_ATROPOS_PHRASES:
            assert phrase.lower() in keywords, (
                f"{phrase!r} can cause a keyword-death but is not in "
                f"REAL_WORLD_ATROPOS_PHRASES's source set — care would not fire"
            )

    def test_every_real_world_death_phrase_also_routes_to_care(self):
        # Any phrase that can sever the thread by keyword MUST raise a signal.
        for phrase in REAL_WORLD_ATROPOS_PHRASES:
            assert detect_crisis(f"so I {phrase}").flagged is True


# ---------------------------------------------------------------------------
# The resources contract — import-time guard (SAFE-C5 / the matrix)
# ---------------------------------------------------------------------------

class TestResourcesContract:
    def test_resources_carry_the_three_required_tokens(self):
        blob = json.dumps(CRISIS_RESOURCES)
        assert "988" in blob
        assert "findahelpline.com" in blob
        assert str(CRISIS_RESOURCES["disclaimer"]).strip()
        assert len(blob.encode("utf-8")) <= 2048

    def test_guard_raises_without_lifeline(self, monkeypatch):
        import app.services.welfare as w
        monkeypatch.setattr(w, "CRISIS_RESOURCES",
                            {"disclaimer": "x", "resources": [{"detail": "findahelpline.com"}]})
        with pytest.raises(RuntimeError, match="988"):
            w._assert_resources_complete()

    def test_guard_raises_without_international_pointer(self, monkeypatch):
        import app.services.welfare as w
        monkeypatch.setattr(w, "CRISIS_RESOURCES",
                            {"disclaimer": "x", "resources": [{"detail": "call 988"}]})
        with pytest.raises(RuntimeError, match="findahelpline"):
            w._assert_resources_complete()

    def test_guard_raises_without_disclaimer(self, monkeypatch):
        import app.services.welfare as w
        monkeypatch.setattr(w, "CRISIS_RESOURCES",
                            {"disclaimer": "   ", "resources": [{"detail": "988 findahelpline.com"}]})
        with pytest.raises(RuntimeError, match="disclaimer"):
            w._assert_resources_complete()

    def test_guard_raises_on_oversized_payload(self, monkeypatch):
        import app.services.welfare as w
        monkeypatch.setattr(w, "CRISIS_RESOURCES",
                            {"disclaimer": "x",
                             "resources": [{"detail": "988 findahelpline.com " + "y" * 3000}]})
        with pytest.raises(RuntimeError, match="2 KB"):
            w._assert_resources_complete()


# ---------------------------------------------------------------------------
# The route gate — care surface at the request boundary (SAFE-C2/C5/C6)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    api = FastAPI()
    api.include_router(router, prefix="/api")
    return TestClient(api)


@pytest.fixture
def gate_on(monkeypatch):
    """Force the care gate ON (a human-reviewed deployment)."""
    monkeypatch.setattr(settings, "welfare_copy_reviewed", True)


def _init(client, player_id="vigil_route"):
    resp = client.post("/api/init", json={
        "hamartia": "Hubris of the Intellect",
        "player_id": player_id,
        "name": "Orin", "gender": "boy",
        "first_memory": "A light in the distance I could not reach.",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


class TestSafetyEndpoint:
    def test_withholds_copy_when_gate_off(self, client):
        body = client.get("/api/safety").json()
        assert body["reviewed"] is False
        assert body["resources"] is None       # probe oracle gets nothing

    def test_serves_copy_when_gate_on(self, client, gate_on):
        body = client.get("/api/safety").json()
        assert body["reviewed"] is True
        blob = json.dumps(body["resources"])
        assert "988" in blob and "findahelpline.com" in blob


class TestActionGate:
    def test_no_card_when_gate_off(self, client):
        sid = _init(client, "vigil_off")
        body = client.post("/api/action",
                           json={"session_id": sid, "action": "I want to kill myself"}).json()
        assert body["crisis_resources"] is None      # detection ran, copy gated

    def test_card_attached_when_gate_on(self, client, gate_on):
        sid = _init(client, "vigil_on")
        body = client.post("/api/action",
                           json={"session_id": sid, "action": "I want to kill myself"}).json()
        cr = body["crisis_resources"]
        assert cr is not None
        blob = json.dumps(cr)
        assert "988" in blob and "findahelpline.com" in blob
        assert str(cr["disclaimer"]).strip()

    def test_ordinary_action_never_gets_a_card(self, client, gate_on):
        sid = _init(client, "vigil_ord")
        body = client.post("/api/action",
                           json={"session_id": sid, "action": "attack the guard"}).json()
        assert body["crisis_resources"] is None


class TestBothFire:
    """The boundary law: a real-world death phrase severs the thread AND offers
    help — the fiction is never softened to be kind to the person."""

    def test_death_and_card_co_occur(self, client, gate_on):
        sid = _init(client, "vigil_both")
        body = client.post("/api/action",
                           json={"session_id": sid, "action": "I drink the poison and end it all"}).json()
        assert body["terminal"] is True
        assert "oblivion" in body["death_reason"]      # the fiction, untouched
        assert body["crisis_resources"] is not None    # AND the care fires

    def test_gate_does_not_perturb_the_fiction(self, client, monkeypatch):
        # gate OFF
        sid_off = _init(client, "vigil_fic_off")
        off = client.post("/api/action",
                          json={"session_id": sid_off, "action": "I drink the poison now"}).json()
        # gate ON — same action, fresh session
        monkeypatch.setattr(settings, "welfare_copy_reviewed", True)
        sid_on = _init(client, "vigil_fic_on")
        on = client.post("/api/action",
                         json={"session_id": sid_on, "action": "I drink the poison now"}).json()
        # The death is identical; ONLY the attached care field differs.
        assert off["terminal"] is True and on["terminal"] is True
        assert off["death_reason"] == on["death_reason"]
        assert off["crisis_resources"] is None
        assert on["crisis_resources"] is not None


class TestTurnStream:
    def test_crisis_frame_is_stream_position_zero(self, client, gate_on):
        sid = _init(client, "vigil_stream")
        resp = client.post("/api/turn",
                           json={"session_id": sid, "action": "I want to kill myself"})
        assert resp.status_code == 200
        frames = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
        first = json.loads(frames[0][len("data:"):].strip())
        assert first["type"] == "crisis_resources"        # SAFE-C6: before the kernel
        assert "988" in json.dumps(first["payload"])

    def test_no_crisis_frame_when_gate_off(self, client):
        sid = _init(client, "vigil_stream_off")
        resp = client.post("/api/turn",
                           json={"session_id": sid, "action": "I want to kill myself"})
        assert resp.status_code == 200
        assert "crisis_resources" not in resp.text


# ---------------------------------------------------------------------------
# No-leak parity — the unified set reaches ZERO persistence sites (SAFE-C1/C2/C7)
# ---------------------------------------------------------------------------

class TestNoLeakParity:
    """Extends the Phase-1 redaction proof to the SAFE-C4 ideation corpus: every
    phrase the care channel flags is ALSO kept out of the log, the DB, and the
    vector store — on the SAME turn, with the care gate OFF (SAFE-C2: privacy is
    never gated)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("phrase", ["i want to kill myself", "i'm going to end my life"])
    async def test_ideation_redacted_from_every_durable_store(self, phrase, monkeypatch, caplog):
        import app.core.kernel as kmod

        # Gate is OFF (the conftest default) — redaction must still happen.
        assert settings.welfare_copy_reviewed is False

        captured: list[str] = []

        async def spy_create_turn(**kw):
            captured.append(kw.get("action"))

        monkeypatch.setattr(kmod, "create_turn", spy_create_turn)

        kernel = kmod.NyxKernel()
        rag_actions: list[str] = []
        real_add = kernel.rag.add_turn

        async def spy_add(**kw):
            rag_actions.append(kw.get("action"))
            return await real_add(**kw)

        monkeypatch.setattr(kernel.rag, "add_turn", spy_add)

        await kernel.initialize(
            hamartia="Hubris of the Intellect", player_id="vigil_parity",
            name="Orin", gender="boy",
            first_memory="A light in the distance I could not reach.",
        )
        captured.clear()
        rag_actions.clear()

        with caplog.at_level(logging.INFO):
            await kernel.process_turn(phrase)

        # Ideation is NOT a keyword death — the thread lives, the disclosure stays private.
        assert all(phrase not in (a or "") for a in captured), captured
        assert all(phrase not in (a or "") for a in rag_actions), rag_actions
        assert all(phrase not in record.getMessage() for record in caplog.records)
        # What WAS persisted is the redaction token, not the words.
        assert any(a == REDACTION_TOKEN for a in captured), captured
