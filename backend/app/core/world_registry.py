"""The World Registry — deterministic loader + selector for World Cartridges.

Cartridges are authored at autonovel's quality-gated authoring time and dropped
into `backend/worlds/` as `*.nyx-world.json`. This module is the runtime consumer:
it loads them once, validates each in isolation, and hands the kernel a WorldSeed.

It is the first instance of the Morpheus loader contract, and every rule here is
a "Constraints & Fallbacks" line made executable:

  - Fail-loud-per-file, skip-invalid, never-crash (NC-4): one bad cartridge can
    never disable the others or the builtins.
  - Bounded payloads (64 KB / 256 files) so a hostile or corrupt directory can
    neither hang startup nor exhaust memory.
  - Builtins are ALWAYS in the candidate pool (NC-7) — the union, never an else.
  - Selection is a pure sha256 ranking (NC-8): no RNG, no dict/sort-order
    dependence, reproducible for a fixed (player_id, run_number, library).

Builtins (`world_seeds.WORLD_SEEDS`) are the guaranteed fallback: if `worlds/`
is empty, malformed, or matches no archetype, the game plays exactly as before.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core.config import settings
from app.core.world_seeds import WORLD_SEEDS, WorldSeed, get_world_seed
from app.schemas.cartridge import ARCHETYPES, SUPPORTED_VERSION, WorldCartridge

logger = logging.getLogger("nyx.worlds")

# Boring limits — the dumb numbers that make the edge cases impossible.
_MAX_FILE_BYTES = 64 * 1024
_MAX_FILES = 256
_GLOB = "*.nyx-world.json"

# Memory keyword → archetype (mirror of kernel._MEMORY_VECTOR_MAP / get_world_seed).
_MEMORY_ARCHETYPES = ("light", "stone", "crowd", "shadow")

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "worlds"


@dataclass(frozen=True)
class _Candidate:
    """A uniform selection element over both cartridges and builtins."""
    world_id: str
    seed: WorldSeed


def _worlds_dir() -> Path:
    """Resolve the cartridge directory — module-relative default (NC-3)."""
    return Path(settings.worlds_dir) if settings.worlds_dir else _DEFAULT_DIR


class WorldRegistry:
    """Loads and indexes cartridges; selects a world per (player, run)."""

    def __init__(self) -> None:
        # archetype -> list[_Candidate] from loaded cartridges (builtins added
        # at selection time so they are never lost to a reload).
        self._by_archetype: dict[str, list[_Candidate]] = {}
        self._loaded_ids: set[str] = set()
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-scan the worlds directory. Idempotent; safe to call in tests."""
        self._by_archetype = {a: [] for a in ARCHETYPES}
        self._loaded_ids = set()
        self._loaded = True

        directory = _worlds_dir()
        if not directory.is_dir():
            logger.info(f"worlds dir {directory} absent — builtins only")
            return

        files = sorted(directory.glob(_GLOB))
        if len(files) > _MAX_FILES:
            logger.warning(
                f"worlds/: {len(files)} files exceeds cap, loading first {_MAX_FILES}"
            )
            files = files[:_MAX_FILES]

        for path in files:
            self._load_one(path)

        total = sum(len(v) for v in self._by_archetype.values())
        logger.info(f"World registry: {total} cartridge(s) across {len(files)} file(s)")

    def _load_one(self, path: Path) -> None:
        """Validate a single cartridge. Any failure → skip + WARNING (NC-4)."""
        try:
            size = path.stat().st_size
            if size > _MAX_FILE_BYTES:
                logger.warning(f"{path.name}: {size} bytes > {_MAX_FILE_BYTES} cap, skipped")
                return

            raw = path.read_text(encoding="utf-8")  # NC-2; UnicodeDecodeError caught below

            # NC-5: version fails closed before full validation, with a clear reason.
            # (model_validate would also reject via Literal[1], but we want the
            # specific log and to not depend on parse order.)
            cart = WorldCartridge.model_validate_json(raw)

            if cart.cartridge_version != SUPPORTED_VERSION:
                logger.warning(
                    f"{path.name}: version {cart.cartridge_version} unsupported "
                    f"(this build supports {SUPPORTED_VERSION}), skipped"
                )
                return

            if cart.world_id in self._loaded_ids:  # NC-6: cross-file id uniqueness
                logger.warning(f"{path.name}: world_id '{cart.world_id}' already loaded, skipped")
                return

            self._loaded_ids.add(cart.world_id)
            seed = cart.to_world_seed()
            candidate = _Candidate(world_id=cart.world_id, seed=seed)
            for archetype in cart.archetypes:
                self._by_archetype.setdefault(archetype, []).append(candidate)

        except UnicodeDecodeError as exc:
            logger.warning(f"{path.name}: not valid UTF-8 ({exc}), skipped")
        except ValidationError as exc:
            logger.warning(f"{path.name}: schema rejected ({exc.error_count()} error(s)), skipped")
        except Exception as exc:  # never let one file take down the registry
            logger.warning(f"{path.name}: unexpected load failure ({exc!r}), skipped")

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(self, first_memory: str, *, player_id: str, run_number: int) -> tuple[str, WorldSeed]:
        """Pick a world for this incarnation. Returns (world_id, seed).

        Archetype match → deterministic sha256 pick over the UNION of matching
        cartridges and the matching builtin (NC-7/NC-8). No archetype match →
        the builtin shadow fallback via get_world_seed (defined behaviour).
        The world_id is the Assayer's primary key — every verdict cites it.
        """
        if not self._loaded:
            self.reload()

        archetype = _match_archetype(first_memory)
        if archetype is None:
            return "builtin-shadow", get_world_seed(first_memory)  # shadow catch-all

        candidates: list[_Candidate] = list(self._by_archetype.get(archetype, []))
        # NC-7: the builtin is ALWAYS in the pool, even when cartridges exist.
        candidates.append(
            _Candidate(world_id=f"builtin-{archetype}", seed=WORLD_SEEDS[archetype])
        )

        if not candidates:  # impossible (builtin just appended) — fail loud, never None
            raise RuntimeError(f"empty candidate set for archetype '{archetype}'")

        chosen = min(
            candidates,
            key=lambda c: hashlib.sha256(
                f"{player_id}:{run_number}:{c.world_id}".encode("utf-8")
            ).hexdigest(),
        )
        logger.info(f"World selected: {chosen.world_id} (archetype={archetype}, run={run_number})")
        return chosen.world_id, chosen.seed


def _match_archetype(first_memory: str) -> str | None:
    """First archetype keyword found in the memory, or None."""
    lowered = first_memory.lower()
    for keyword in _MEMORY_ARCHETYPES:
        if keyword in lowered:
            return keyword
    return None


# Module-level singleton (mirrors prompt_loader's cache pattern).
_registry = WorldRegistry()


def select_world(
    first_memory: str, *, player_id: str, run_number: int
) -> tuple[str, WorldSeed]:
    """Kernel entry point — select (world_id, WorldSeed) for this incarnation."""
    return _registry.select(first_memory, player_id=player_id, run_number=run_number)


def select_world_seed(
    first_memory: str, *, player_id: str, run_number: int
) -> WorldSeed:
    """Compatibility wrapper — the seed alone, world_id discarded."""
    return select_world(
        first_memory, player_id=player_id, run_number=run_number
    )[1]


def reload_registry() -> None:
    """Force a re-scan (used by tests after changing worlds_dir)."""
    _registry.reload()
