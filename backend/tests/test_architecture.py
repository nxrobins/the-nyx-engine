"""Architectural fitness — the determinism gradient is executable, not aspirational.

The Nyx Engine's defining invariant is authority inversion: the prose/model layer
holds the LOWEST authority, and the deterministic consequence layer — soul math,
pressure, doom, oaths, legacy, the promise/beat ledger, canon mutation — decides
what is true with NO model in the loop. That is the whole reason an AI can author
tragedy here without being able to cheat the consequences.

Nothing previously guarded it. These tests pin the invariant in the IMPORT GRAPH
so a future change can't quietly wire a model call into a consequence service:
the determinism gradient becomes a build-time check, not a code-review hope.

Pure-additive, deterministic, hermetic — parses source with `ast` (so a `from`
word inside a docstring is correctly ignored, which a grep would not be).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parent.parent / "app"

# The pure deterministic consequence/state layer. Each of these computes or
# mutates the consequence economy mid-life and MUST stay model-free — importing
# the agent tier or the LLM wrapper here would collapse the determinism gradient
# (the prose LLM could then reach back into what decides truth).
#
# Deliberately NOT listed: `core/resolver.py` and `core/kernel.py` (they
# ORCHESTRATE the model-facing agents — that is their job, one tier up), and
# `services/scribe_gate.py` (it reuses Momus's pure-regex `_detect_anachronisms`
# helper, the one sanctioned deterministic borrow from the agent module).
MODEL_FREE_MODULES = [
    "services/soul_math.py",
    "services/pressure.py",
    "services/doom.py",
    "services/oath_engine.py",
    "services/oath_parser.py",
    "services/legacy.py",
    "services/canon.py",
    "services/promise_engine.py",
    "services/beat_gate.py",
    # More pure consequence/state modules that MUST stay model-free (audit M7):
    # the adult director (docstring promises "Zero LLM tokens"), the hamartia
    # engine (assigns the permanent flaw deterministically), and the Assayer
    # (its whole charter is "no LLM judges a life").
    "core/director.py",
    "services/hamartia_engine.py",
    "services/assayer.py",
    # THE PULSE: authored-vignette selection/binding and the hand-authored
    # pools — cheap beats are the MOST deterministic; no model may ever
    # compose or pick a vignette.
    "services/vignettes.py",
    "core/vignette_pools.py",
    # The Vigil's per-turn crisis detector: the highest-stakes safety decision
    # in the engine and deterministic by design. Pinned model-free so no future
    # "LLM classifier" can be wired into detect_crisis via the sanctioned
    # app.services.llm wrapper (which the single-choke-point test misses, since
    # it only forbids a DIRECT litellm import). (audit M4)
    "services/welfare.py",
]


def _is_model_layer(module: str) -> bool:
    """True if `module` is the LLM wrapper or the model-facing agent tier.

    `app.services.llm` is the sole sanctioned wrapper around litellm; everything
    under `app.agents` is model-facing (Clotho/Nemesis/Eris/Sophia/...).
    """
    return (
        module == "litellm"
        or module.startswith("litellm.")
        or module == "app.services.llm"
        or module == "app.agents"
        or module.startswith("app.agents.")
    )


def _imported_modules(path: Path) -> set[str]:
    """Every fully-qualified module name a source file imports (via AST)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # package of this file, e.g. backend/app/services/x.py -> ("app", "services").
    # Only relative imports need it; a file outside the app tree (a test fixture)
    # has no package, and its absolute imports resolve without one.
    try:
        pkg = list(path.relative_to(_APP.parent).with_suffix("").parts[:-1])
    except ValueError:
        pkg = []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — resolve to an absolute name
                base = pkg[: len(pkg) - (node.level - 1)]
                parts = base + ([node.module] if node.module else [])
                module = ".".join(parts)
            elif node.module:
                module = node.module
            else:
                continue
            found.add(module)
            # Also record each imported NAME as a fully-qualified module. This
            # closes the `from app.services import llm` hole: that records only
            # "app.services" above, which the layer check does not flag — but the
            # thing imported IS app.services.llm. `from app import agents` → the
            # same for "app.agents". (audit M7)
            for alias in node.names:
                if alias.name != "*":
                    found.add(f"{module}.{alias.name}")
    return found


class TestDeterminismGradient:
    """The consequence layer must never depend on the model layer."""

    def test_guarded_set_exists_and_is_not_silently_shrunk(self):
        # A renamed/deleted module would make its parametrized case vanish; pin
        # the floor so the guard can't be hollowed out unnoticed.
        assert len(MODEL_FREE_MODULES) >= 13
        for rel in MODEL_FREE_MODULES:
            assert (_APP / rel).exists(), f"guarded module moved or renamed: {rel}"

    @pytest.mark.parametrize("rel", MODEL_FREE_MODULES)
    def test_consequence_module_is_model_free(self, rel: str):
        offenders = sorted(
            m for m in _imported_modules(_APP / rel) if _is_model_layer(m)
        )
        assert not offenders, (
            f"{rel} imports the model layer {offenders}. The determinism gradient "
            f"forbids a consequence service depending on agents/LLM — the prose "
            f"layer has the LOWEST authority and must not reach into what decides "
            f"truth. If the architecture truly changed, revisit this invariant "
            f"deliberately rather than relaxing the test."
        )

    def test_litellm_has_a_single_choke_point(self):
        """Only `services/llm.py` may import litellm — one auditable seam for
        every model call in the engine."""
        importers = sorted(
            py.relative_to(_APP).as_posix()
            for py in _APP.rglob("*.py")
            if any(
                m == "litellm" or m.startswith("litellm.")
                for m in _imported_modules(py)
            )
        )
        assert importers == ["services/llm.py"], (
            f"litellm must be imported only by services/llm.py (the sole model "
            f"wrapper, so every model call has one auditable seam); found: {importers}"
        )

    def test_from_import_idiom_is_not_a_blind_spot(self, tmp_path):
        """`from app.services import llm` / `from app import agents` must be seen.

        These record only "app.services" / "app" as the module, which the layer
        check does not flag — yet the imported NAME is the model layer. If a
        consequence module used this idiom to reach the LLM wrapper, the guard
        would have missed it (audit M7). This pins that the extractor resolves the
        imported name to its full path so `_is_model_layer` catches it.
        """
        f = tmp_path / "sneaky.py"
        f.write_text(
            "from app.services import llm\n"
            "from app import agents\n"
            "from app.agents import nemesis\n",
            encoding="utf-8",
        )
        found = _imported_modules(f)
        assert "app.services.llm" in found
        assert "app.agents" in found
        assert any(_is_model_layer(m) for m in found)
