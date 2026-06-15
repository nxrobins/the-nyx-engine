"""CLI: regenerate backend/sim/baseline.friction.json (deterministic bytes).

Run ``python -m sim.emit_artifact`` from backend/. The output is a checked-in
regression artifact: a reviewer who touches any consequence threshold sees a
visible diff here. Idempotent — same seeds → byte-identical file (sorted keys,
rounded floats).

Standalone (outside pytest) it configures its own hermetic runtime; the
verdicts are computed in memory, so books/assays land in a throwaway temp dir
and never the repo.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import tempfile

_BASELINE = pathlib.Path(__file__).resolve().parent / "baseline.friction.json"

_MODEL_FIELDS = (
    "clotho_model", "lachesis_model", "nemesis_model", "eris_model",
    "hypnos_model", "chronicler_model", "morpheus_model", "scribe_model",
)


def configure_hermetic() -> None:
    """Force mock + zero latency + off-repo artifact dirs (for standalone runs)."""
    from app.core.config import settings

    for field in _MODEL_FIELDS:
        setattr(settings, field, "mock")
    settings.mock_latency_scale = 0.0
    settings.database_url = ""
    settings.sqlite_store_path = ""
    tmp = tempfile.mkdtemp(prefix="nyx_sim_")
    settings.books_dir = str(pathlib.Path(tmp) / "books")
    settings.assays_dir = str(pathlib.Path(tmp) / "assays")


async def build_artifact() -> dict:
    """Run the corpus + red-team and assemble the artifact dict."""
    from sim.corpus import PARAPHRASE_PAIRS, SCRIPTS
    from sim.metrics import build_report
    from sim.red_team import score_smuggle_throughs
    from sim.runner import run_corpus

    outcomes = await run_corpus(SCRIPTS)
    report = build_report(outcomes).to_dict()           # raises on out-of-enum bucket
    smuggle = score_smuggle_throughs(PARAPHRASE_PAIRS).to_dict()
    return {"friction": report, "keyword_smuggle": smuggle}


def serialize(artifact: dict) -> str:
    """Deterministic bytes: sorted keys, indent 2, trailing newline."""
    return json.dumps(artifact, indent=2, sort_keys=True) + "\n"


def main() -> int:
    configure_hermetic()
    artifact = asyncio.run(build_artifact())
    text = serialize(artifact)
    _BASELINE.write_text(text, encoding="utf-8")
    print(f"Wrote {_BASELINE} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
