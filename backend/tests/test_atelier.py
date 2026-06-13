"""The Atelier — the producer side of the plate law.

The load-bearing contract: every filename plan_plates emits must satisfy
the consumer's _PLATE_RE, NPC stems must equal the canon npc_ids, and seeds
must be deterministic-per-plate. Execution is tested with mocked generation/
download — staging-only, atomic, failure-counted, oversize-rejected (AT-E2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.tools.atelier as atelier
from app.schemas.cartridge import WorldCartridge
from app.services.canon import bootstrap_canon
from app.services.plates import _PLATE_RE
from app.tools.atelier import PlateJob, execute, find_cartridge, main, plan_plates

WORLDS_DIR = Path(__file__).resolve().parent.parent / "worlds"


def _builtin_cartridges() -> list[WorldCartridge]:
    return [
        WorldCartridge.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(WORLDS_DIR.glob("*.nyx-world.json"))
    ]


# ---------------------------------------------------------------------------
# The plan — pure, deterministic, lawful
# ---------------------------------------------------------------------------

class TestPlan:
    def test_every_filename_satisfies_the_consumer_law(self):
        carts = _builtin_cartridges()
        assert len(carts) == 4  # the builtins ship as cartridges
        for cart in carts:
            for job in plan_plates(cart):
                assert _PLATE_RE.fullmatch(job.filename), (cart.world_id, job.filename)
                assert job.filename.endswith(".jpg")  # BFL can't do webp → jpeg

    def test_plan_is_deterministic(self):
        cart = _builtin_cartridges()[0]
        assert plan_plates(cart) == plan_plates(cart)

    def test_seeds_are_deterministic_and_per_plate(self):
        cart = _builtin_cartridges()[0]
        a = {j.filename: j.seed for j in plan_plates(cart)}
        b = {j.filename: j.seed for j in plan_plates(cart)}
        assert a == b  # same world → identical seeds (reproducible)
        assert len(set(a.values())) == len(a)  # varied across plates
        assert all(0 <= s < 2**32 for s in a.values())  # 32-bit, BFL's range

    def test_npc_stems_are_canon_npc_ids_verbatim(self):
        for cart in _builtin_cartridges():
            canon = bootstrap_canon(cart.to_world_seed(), "Orin", "boy")
            stems = {
                j.filename.rsplit(".", 1)[0]
                for j in plan_plates(cart)
                if j.filename.startswith("npc_")
            }
            assert stems <= set(canon.npcs.keys()), cart.world_id
            assert len(stems) == len(cart.family)

    def test_prompts_are_cartridge_sourced(self):
        cart = _builtin_cartridges()[0]
        jobs = {j.filename.rsplit(".", 1)[0]: j for j in plan_plates(cart)}
        assert cart.settlement in jobs["settlement"].prompt
        assert cart.region in jobs["settlement"].prompt
        assert cart.home_location.name in jobs["home"].prompt
        assert cart.faction.name in jobs["faction"].prompt
        for npc in cart.family:
            stem = next(s for s in jobs if s.startswith("npc_") and npc.name.split()[0].lower() in s)
            assert npc.name in jobs[stem].prompt
            assert npc.trait in jobs[stem].prompt

    def test_people_descriptor_in_portraits_and_factions(self):
        # Art direction: the people of the Age of Ash are Black/Brown — applied
        # to every portrait and faction crowd, and never truncated by the cap.
        for cart in _builtin_cartridges():
            for job in plan_plates(cart):
                stem = job.filename.rsplit(".", 1)[0]
                if stem.startswith("npc_") or stem == "faction":
                    assert atelier.PEOPLE_DESCRIPTOR in job.prompt, job.filename

    def test_prompts_carry_the_world_mood(self):
        cart = _builtin_cartridges()[0]
        mood = atelier._world_mood(cart)
        assert mood  # builtins have an active_situation
        jobs = {j.filename.rsplit(".", 1)[0]: j for j in plan_plates(cart)}
        # the shared mood threads through the world-scale plates
        assert mood[:24] in jobs["settlement"].prompt

    def test_prompts_are_length_bounded(self):
        for cart in _builtin_cartridges():
            for job in plan_plates(cart):
                assert len(job.prompt) <= atelier.MAX_PROMPT_CHARS

    def test_only_filters_by_stem(self):
        cart = _builtin_cartridges()[0]
        jobs = plan_plates(cart, only={"settlement", "home"})
        assert sorted(j.filename for j in jobs) == ["home.jpg", "settlement.jpg"]

    def test_job_cap_refuses_before_any_call(self, monkeypatch):
        monkeypatch.setattr(atelier, "MAX_JOBS", 2)
        with pytest.raises(ValueError, match="cap"):
            plan_plates(_builtin_cartridges()[0])


# ---------------------------------------------------------------------------
# Finding the cartridge
# ---------------------------------------------------------------------------

class TestFindCartridge:
    def test_finds_a_builtin_by_world_id(self):
        cart_ids = {c.world_id for c in _builtin_cartridges()}
        some_id = sorted(cart_ids)[0]
        found = find_cartridge(some_id)
        assert found is not None
        assert found.world_id == some_id

    def test_unknown_id_returns_none(self):
        assert find_cartridge("no-such-world") is None


# ---------------------------------------------------------------------------
# Execution — staging-only, atomic, jpeg+seed, oversize-rejected
# ---------------------------------------------------------------------------

@pytest.fixture
def staging(tmp_path, monkeypatch):
    """Aim the atelier's staging (and the worlds dir) at tmp_path."""
    monkeypatch.setattr(atelier, "_worlds_dir", lambda: tmp_path / "worlds")
    return tmp_path / "worlds" / "art" / "_staging"


class TestExecute:
    @pytest.mark.asyncio
    async def test_stages_jpeg_with_seed_atomically(self, staging, monkeypatch):
        seeds: list[int] = []

        async def fake_generate(prompt, api_key, model="x", output_format=None, seed=None):
            assert output_format == "jpeg"  # BFL can't do webp; jpeg is directly promotable
            seeds.append(seed)
            return "https://bfl.example/result.jpg"

        async def fake_download(client, url):
            return b"\xff\xd8\xff-jpeg-bytes"

        monkeypatch.setattr(atelier, "generate_image", fake_generate)
        monkeypatch.setattr(atelier, "_download", fake_download)

        jobs = [PlateJob("settlement.jpg", "p", seed=4242), PlateJob("npc_mara.jpg", "q", seed=99)]
        failed = await execute(jobs, "w-test", api_key="k")

        assert failed == 0
        assert seeds == [4242, 99]  # each plate's seed reaches BFL
        world_staging = staging / "w-test"
        assert (world_staging / "settlement.jpg").read_bytes() == b"\xff\xd8\xff-jpeg-bytes"
        assert (world_staging / "npc_mara.jpg").exists()
        assert list(world_staging.glob("*.tmp")) == []  # atomic — no temp left
        assert not (staging.parent / "w-test").exists()  # staging only; live dir untouched

    @pytest.mark.asyncio
    async def test_generation_failure_counts_and_writes_nothing(self, staging, monkeypatch):
        async def dead_generate(prompt, api_key, model="x", output_format=None, seed=None):
            return ""  # moderation/error/timeout already collapsed to "" in generate_image

        monkeypatch.setattr(atelier, "generate_image", dead_generate)
        failed = await execute([PlateJob("settlement.jpg", "p", seed=1)], "w-test", api_key="k")
        assert failed == 1
        assert not (staging / "w-test" / "settlement.jpg").exists()

    @pytest.mark.asyncio
    async def test_download_failure_never_repays_generation(self, staging, monkeypatch):
        calls = {"gen": 0}

        async def counting_generate(prompt, api_key, model="x", output_format=None, seed=None):
            calls["gen"] += 1
            return "https://bfl.example/result.jpg"

        async def dead_download(client, url):
            return None

        monkeypatch.setattr(atelier, "generate_image", counting_generate)
        monkeypatch.setattr(atelier, "_download", dead_download)

        failed = await execute([PlateJob("settlement.jpg", "p", seed=1)], "w-test", api_key="k")
        assert failed == 1
        assert calls["gen"] == 1  # the paid call happened exactly once

    @pytest.mark.asyncio
    async def test_oversize_fails_and_is_not_staged(self, staging, monkeypatch, caplog):
        # AT-E2: a plate over the serve cap fails the job and is NOT staged —
        # the curator never promotes something the serve gate would 413.
        async def fake_generate(prompt, api_key, model="x", output_format=None, seed=None):
            return "https://bfl.example/result.jpg"

        async def big_download(client, url):
            return b"\x00" * (atelier.SERVE_CAP_BYTES + 1)

        monkeypatch.setattr(atelier, "generate_image", fake_generate)
        monkeypatch.setattr(atelier, "_download", big_download)

        with caplog.at_level("WARNING", logger="nyx.atelier"):
            failed = await execute([PlateJob("settlement.jpg", "p", seed=1)], "w-test", api_key="k")

        assert failed == 1
        assert not (staging / "w-test" / "settlement.jpg").exists()
        assert any("serve cap" in r.message for r in caplog.records)

    def test_write_atomic_overwrites_idempotently(self, tmp_path):
        target = tmp_path / "a" / "settlement.jpg"
        atelier._write_atomic(target, b"one")
        atelier._write_atomic(target, b"two")
        assert target.read_bytes() == b"two"
        assert list(target.parent.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_dry_run_calls_nothing_and_exits_zero(self, monkeypatch, capsys):
        async def forbidden(*args, **kwargs):
            raise AssertionError("dry run must not call BFL")

        monkeypatch.setattr(atelier, "generate_image", forbidden)
        world_id = sorted(c.world_id for c in _builtin_cartridges())[0]
        code = main(["--world", world_id, "--dry-run"])
        assert code == 0
        out = capsys.readouterr().out
        assert "settlement.jpg" in out
        assert "seed" in out
        assert "dry run" in out

    def test_unknown_world_refuses_exit_2(self):
        assert main(["--world", "no-such-world", "--dry-run"]) == 2

    def test_only_matching_nothing_refuses_exit_2(self):
        world_id = sorted(c.world_id for c in _builtin_cartridges())[0]
        assert main(["--world", world_id, "--only", "nope", "--dry-run"]) == 2

    def test_missing_api_key_refuses_exit_2(self, monkeypatch):
        monkeypatch.setattr(atelier.settings, "bfl_api_key", "")
        world_id = sorted(c.world_id for c in _builtin_cartridges())[0]
        assert main(["--world", world_id]) == 2
