"""The Plates — manifest + serve gates (The Ink, Layer 1).

First endpoint-level tests in the suite: a minimal FastAPI app + TestClient,
never importing main.py (its lifespan would init the DB pool). The art dir
is a tmp_path injected through the named seam (plates._art_root).
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.plates as plates
from app.api.routes import router

WORLD = "thornwell-test"


@pytest.fixture
def art_dir(tmp_path, monkeypatch):
    """Point the named seam at tmp_path; return this world's art dir."""
    root = tmp_path / "art"
    monkeypatch.setattr(plates, "_art_root", lambda wid: root / wid)
    world_dir = root / WORLD
    world_dir.mkdir(parents=True)
    return world_dir


@pytest.fixture
def client(art_dir):
    api = FastAPI()
    api.include_router(router, prefix="/api")
    return TestClient(api)


def _write(path, size=64):
    path.write_bytes(b"\x89PNG" + b"\x00" * max(size - 4, 0))


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------

class TestManifest:
    def test_missing_dir_is_empty_not_error(self, client):
        resp = client.get("/api/plates/no-such-world")
        assert resp.status_code == 200
        body = resp.json()
        assert body["plates"] == {}
        assert body["skipped"] == []

    def test_invalid_world_id_is_empty(self, client):
        for bad in ("UPPER", "ab", "has space", "..", "a/../b"):
            resp = client.get(f"/api/plates/{bad}")
            # path traversal shapes may 404 at the router; the rest empty-manifest
            assert resp.status_code in (200, 404)
            if resp.status_code == 200:
                assert resp.json()["plates"] == {}

    def test_valid_plates_listed_with_server_built_urls(self, client, art_dir):
        _write(art_dir / "settlement.png")
        _write(art_dir / "home.webp")
        _write(art_dir / "npc_mara.png")
        body = client.get(f"/api/plates/{WORLD}").json()
        assert body["plates"]["settlement"] == f"/api/plates/{WORLD}/settlement.png"
        assert body["plates"]["home"] == f"/api/plates/{WORLD}/home.webp"
        assert body["plates"]["npc_mara"] == f"/api/plates/{WORLD}/npc_mara.png"
        assert body["skipped"] == []

    def test_unlawful_names_skipped_with_reason(self, client, art_dir):
        _write(art_dir / "settlement.png")
        _write(art_dir / "notes.txt")
        _write(art_dir / "scene.jpg")          # jpeg is not in the law
        _write(art_dir / "NPC_Mara.png")       # uppercase
        _write(art_dir / "settlement (1).png")  # the curator's classic
        body = client.get(f"/api/plates/{WORLD}").json()
        assert list(body["plates"]) == ["settlement"]
        skipped = {s["file"] for s in body["skipped"]}
        assert skipped == {"notes.txt", "scene.jpg", "NPC_Mara.png", "settlement (1).png"}
        assert all("name" in s["reason"] for s in body["skipped"])

    def test_oversize_skipped_with_webp_nudge(self, client, art_dir):
        _write(art_dir / "settlement.png", size=plates.MAX_PLATE_BYTES + 1)
        body = client.get(f"/api/plates/{WORLD}").json()
        assert body["plates"] == {}
        assert "oversize" in body["skipped"][0]["reason"]
        assert "webp" in body["skipped"][0]["reason"]

    def test_directory_cap_serves_first_64_sorted(self, client, art_dir):
        for i in range(70):
            _write(art_dir / f"npc_a{i:03d}.png")
        body = client.get(f"/api/plates/{WORLD}").json()
        assert len(body["plates"]) == plates.MAX_DIR_ENTRIES
        assert "npc_a000" in body["plates"]
        assert "npc_a069" not in body["plates"]

    def test_scan_exception_degrades_never_500(self, client, art_dir, monkeypatch):
        def locked(_):
            raise PermissionError("the Defender holds the door")

        monkeypatch.setattr(plates.os, "listdir", locked)
        resp = client.get(f"/api/plates/{WORLD}")
        assert resp.status_code == 200      # INK-E2: degraded, not dead
        assert resp.json()["plates"] == {}

    def test_no_store_header(self, client):
        resp = client.get(f"/api/plates/{WORLD}")
        assert resp.headers["cache-control"] == "no-store"

    def test_rescans_every_request_no_listing_cache(self, client, art_dir):
        assert client.get(f"/api/plates/{WORLD}").json()["plates"] == {}
        _write(art_dir / "settlement.png")  # curation between requests
        assert "settlement" in client.get(f"/api/plates/{WORLD}").json()["plates"]


# ---------------------------------------------------------------------------
# The serve gate
# ---------------------------------------------------------------------------

class TestServe:
    def test_serves_lawful_plate_with_media_type_and_cache(self, client, art_dir):
        _write(art_dir / "settlement.png")
        resp = client.get(f"/api/plates/{WORLD}/settlement.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["cache-control"] == "public, max-age=300"
        assert resp.content.startswith(b"\x89PNG")

    def test_webp_media_type(self, client, art_dir):
        _write(art_dir / "home.webp")
        resp = client.get(f"/api/plates/{WORLD}/home.webp")
        assert resp.headers["content-type"] == "image/webp"

    def test_missing_plate_404(self, client):
        assert client.get(f"/api/plates/{WORLD}/settlement.png").status_code == 404

    def test_unlawful_names_404_before_filesystem(self, client, art_dir):
        _write(art_dir / "settlement.png")
        for bad in (
            "settlement.jpg", "SETTLEMENT.png", "npc_..png",
            "npc_M.png", "anything.png", "settlement.png.bak",
        ):
            assert client.get(f"/api/plates/{WORLD}/{bad}").status_code == 404, bad

    def test_traversal_never_yields_the_file(self, client, art_dir):
        # The secret sits one level above the world's art dir. Every
        # traversal shape must fail somewhere in the stack — the route,
        # the filename law, or the world-id law (httpx normalizes raw
        # ../ so that shape lands on the manifest endpoint, whose
        # world-id regex rejects "secret.png"). The invariant: the
        # secret's bytes never come back.
        secret = art_dir.parent / "secret.png"
        _write(secret, size=128)
        secret_bytes = secret.read_bytes()
        for path in (
            f"/api/plates/{WORLD}/..%2Fsecret.png",
            f"/api/plates/{WORLD}/%2e%2e/secret.png",
            f"/api/plates/{WORLD}/../secret.png",
            "/api/plates/../art/secret.png",
        ):
            resp = client.get(path)
            assert resp.content != secret_bytes, path
            if resp.status_code == 200:  # normalized onto the manifest endpoint
                assert resp.json()["plates"] == {}, path

    def test_oversize_413_at_serve_time(self, client, art_dir):
        # INK-E3: the file door enforces the size law even when the
        # manifest never advertised the file.
        _write(art_dir / "settlement.png", size=plates.MAX_PLATE_BYTES + 1)
        assert client.get(f"/api/plates/{WORLD}/settlement.png").status_code == 413

    def test_serve_exception_404_never_500(self, client, art_dir, monkeypatch):
        _write(art_dir / "settlement.png")

        real_is_file = plates.Path.is_file

        def locked(self):
            if self.name == "settlement.png":
                raise OSError("locked")
            return real_is_file(self)

        monkeypatch.setattr(plates.Path, "is_file", locked)
        assert client.get(f"/api/plates/{WORLD}/settlement.png").status_code == 404


# ---------------------------------------------------------------------------
# Containment (the realpath law, unit-level — symlinks need privileges on
# Windows, so the law is tested directly)
# ---------------------------------------------------------------------------

class TestContainment:
    def test_inside(self, tmp_path):
        root = tmp_path / "art" / "w"
        root.mkdir(parents=True)
        assert plates._contained(root / "settlement.png", root)

    def test_outside_via_dotdot(self, tmp_path):
        root = tmp_path / "art" / "w"
        root.mkdir(parents=True)
        assert not plates._contained(root / ".." / "secret.png", root)

    def test_sibling_root_prefix_not_fooled(self, tmp_path):
        # /art/w-evil must not count as inside /art/w (commonpath, not startswith)
        root = tmp_path / "art" / "w"
        evil = tmp_path / "art" / "w-evil"
        root.mkdir(parents=True)
        evil.mkdir(parents=True)
        assert not plates._contained(evil / "x.png", root)

    @pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
    def test_symlink_escape_rejected(self, tmp_path):
        root = tmp_path / "art" / "w"
        root.mkdir(parents=True)
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"x")
        link = root / "settlement.png"
        link.symlink_to(outside)
        assert not plates._contained(link, root)
