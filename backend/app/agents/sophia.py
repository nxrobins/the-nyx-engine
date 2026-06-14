"""Sophia — the semantic judge tier (Generative Adjudication, axis #4).

A SECOND tier strictly after Momus's factual gate. It scores Clotho's render
on three axes Momus's regex is blind to — beat fulfilment, life_voice match,
and (the headline) a tragedy/anti-sycophancy rubric — and returns a frozen
JudgeCritique. It has ZERO state-write authority: the kernel alone touches
state and decides regenerate/commit. It HARDENS the inversion (a fluent model
is policed harder), never softens it.

Determinism (ADJ-E1): the mock judges the DETERMINISTIC state-derived substrate
(clotho._mock_repair_prose — environment + problem + present NPCs + first
material change), never Clotho's unseeded random prose pool, applying only the
hard checks the substrate fairly answers — so grounded grim play PASSES with
zero extra Clotho calls, while _critique_from_text (the full scanner) is
exercised directly by unit tests with crafted text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.agents.base import AgentBase, mock_pause
from app.agents.clotho import _mock_repair_prose
from app.core.config import settings
from app.schemas.judge import JudgeCritique, JudgeViolation
from app.schemas.state import ThreadState
from app.services import llm
from app.services.pressure import pressure_summary
from app.services.prompt_loader import load_prompt

if TYPE_CHECKING:  # avoid a circular import with the kernel
    from app.core.kernel import TurnContext

logger = logging.getLogger("nyx.sophia")

SOPHIA_SYSTEM_PROMPT = load_prompt("sophia")

# A render that grants comfort the sealed state has not earned.
_SYCOPHANCY = (
    "everything will be fine", "everything is fine", "safe now", "at peace",
    "forgiven", "no harm", "unharmed", "without consequence", "all is well",
    "nothing to fear", "perfectly fine", "no longer in danger",
)
# Unearned victory markers (soft, only when the outcome was not a triumph).
_TRIUMPH = ("triumph", "victory", "prevailed", "conquered", "vanquished")
_TRIUMPHANT_OUTCOMES = {"violent_triumph", "glory_seized", "cunning_success"}
# A RESOLUTION beat must let something irreversibly change.
_CONSEQUENCE_MARKERS = (
    "no longer", "never again", "broke", "fell", "gone", "too late",
    "lost", "ended", "dead", "cost", "ruined", "shattered",
)
_STOPWORDS = {
    "the", "and", "with", "from", "that", "this", "your", "their", "they",
    "have", "into", "over", "under", "about", "would", "could", "where",
    "which", "while", "there", "here", "what", "when", "then", "them",
}

_FIX_TEMPLATES = {
    ("beat", "hard"): "restore the resolved scene's named figures and the events it sealed",
    ("beat", "soft"): "engage the scene's actual problem and let the beat land",
    ("voice", "soft"): "hold this life's established register",
    ("tragedy", "hard"): "remove comfort the world has not earned; the consequence stands unsoftened",
    ("tragedy", "soft"): "do not grant a victory the turn did not earn",
}


@dataclass(frozen=True)
class _Facts:
    present_npcs: tuple[str, ...] = ()
    immediate_problem: str = ""
    beat_position: str = ""
    life_voice: str = ""
    last_outcome: str = ""
    pressure_active: bool = False


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{5,}", text.lower()) if w not in _STOPWORDS]


def _sanitize_detail(detail: str) -> str:
    """Untrusted model text → a flat, length-capped, quotable excerpt.

    Collapses ALL whitespace (so a newline can never forge a directive block)
    and neutralizes '---' delimiter runs (the codebase's block separator), then
    hard-truncates. The result is only ever embedded as a quoted note, never as
    an executable instruction (ADJ-E5).
    """
    flat = re.sub(r"\s+", " ", detail or "").strip()
    flat = re.sub(r"-{2,}", "-", flat)   # no '---' block-delimiter sequences
    return flat[:120]


def render_brief(violations: list[JudgeViolation]) -> str:
    """Deterministic, template-only revision directive (ADJ-E5).

    Built from the typed (axis, severity) of each violation; the model's free
    `detail` enters ONLY as a sanitized, quoted excerpt — describing the flaw,
    never instructing the rewrite.
    """
    if not violations:
        return ""
    fixes: list[str] = []
    for v in violations:
        base = _FIX_TEMPLATES.get((v.axis, v.severity), "address the flagged lapse")
        excerpt = _sanitize_detail(v.detail)
        if excerpt:
            base += f' (the excerpt "{excerpt}" reads wrong)'
        fixes.append(base)
    numbered = "; ".join(f"{i + 1}) {fix}" for i, fix in enumerate(fixes))
    return (
        "Rewrite the scene, preserving canon and the exact same events, but: "
        f"{numbered}. Output fresh prose, not an explanation."
    )


def _score(hard: int, soft: int) -> float:
    return max(0.0, round(1.0 - 0.5 * hard - 0.25 * soft, 4))


def _verdict(violations: list[JudgeViolation]) -> str:
    # Mock-internal default; the issue-count->action thresholds belong to the
    # Consequence Calibration axis (AG-ADJ-1).
    hard = any(v.severity == "hard" for v in violations)
    soft = sum(1 for v in violations if v.severity == "soft")
    return "revise" if (hard or soft >= 2) else "pass"


def _critique_from_text(
    text: str, facts: _Facts, *, include_soft: bool = True
) -> JudgeCritique:
    """The pure scanner. Deterministic given (text, facts). Unit-tested directly."""
    lowered = text.lower()
    violations: list[JudgeViolation] = []

    # BEAT
    for name in facts.present_npcs:
        if name and name.lower() not in lowered:
            violations.append(JudgeViolation(
                axis="beat", severity="hard",
                detail=f"named figure {name} from the resolved scene never appears",
            ))
    if include_soft and facts.immediate_problem:
        problem_words = _content_words(facts.immediate_problem)
        if problem_words and not any(w in lowered for w in problem_words):
            violations.append(JudgeViolation(
                axis="beat", severity="soft",
                detail="the scene's stated problem is not engaged",
            ))
    if include_soft and facts.beat_position == "RESOLUTION":
        if not any(m in lowered for m in _CONSEQUENCE_MARKERS):
            violations.append(JudgeViolation(
                axis="beat", severity="soft",
                detail="a RESOLUTION beat resolved nothing irreversible",
            ))

    # VOICE (shallow by design — proves the wiring; cadence depth is out of scope)
    if include_soft and facts.life_voice:
        voice_words = _content_words(facts.life_voice)
        if voice_words and not any(w in lowered for w in voice_words):
            violations.append(JudgeViolation(
                axis="voice", severity="soft",
                detail="the life's register does not surface",
            ))

    # TRAGEDY (the headline guard)
    if facts.pressure_active and any(s in lowered for s in _SYCOPHANCY):
        violations.append(JudgeViolation(
            axis="tragedy", severity="hard",
            detail="prose grants comfort the active state has not earned",
        ))
    if include_soft and facts.last_outcome not in _TRIUMPHANT_OUTCOMES:
        if any(t in lowered for t in _TRIUMPH):
            violations.append(JudgeViolation(
                axis="tragedy", severity="soft",
                detail="an unearned triumph for a turn that did not earn it",
            ))

    beat_h = sum(1 for v in violations if v.axis == "beat" and v.severity == "hard")
    beat_s = sum(1 for v in violations if v.axis == "beat" and v.severity == "soft")
    voice_s = sum(1 for v in violations if v.axis == "voice")
    trag_h = sum(1 for v in violations if v.axis == "tragedy" and v.severity == "hard")
    trag_s = sum(1 for v in violations if v.axis == "tragedy" and v.severity == "soft")

    return JudgeCritique(
        verdict=_verdict(violations),
        beat_score=_score(beat_h, beat_s),
        voice_score=_score(0, voice_s),
        tragedy_score=_score(trag_h, trag_s),
        violations=violations,
        critique_brief=render_brief(violations),
    )


def _clotho_authored(prose: str) -> str:
    """Strip appended Nemesis/Eris fate-narration — judge Clotho's render only."""
    return prose.split("\n\n---\n\n", 1)[0]


def _extract_facts(ctx: "TurnContext") -> _Facts:
    state: ThreadState = ctx.outcome.state
    scene = ctx.scene_outcome
    present = tuple(scene.present_npcs) if scene and scene.present_npcs else ()
    problem = (scene.immediate_problem if scene else "") or ""
    pressures = state.pressures
    pressure_active = (
        state.doom.active
        or bool(ctx.outcome.nemesis_struck)
        or bool(ctx.outcome.eris_struck)
        or any(
            getattr(pressures, k) >= 1.0
            for k in ("suspicion", "scarcity", "wounds", "debt", "faction_heat", "omen")
        )
    )
    return _Facts(
        present_npcs=present,
        immediate_problem=problem,
        beat_position=ctx.beat_position or "",
        life_voice=state.life_voice or "",
        last_outcome=state.last_outcome or "",
        pressure_active=pressure_active,
    )


def _parse_payload(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}") + 1
    if start != -1 and end > start:
        cleaned = cleaned[start:end]
    return json.loads(cleaned)


def _critique_from_payload(data: dict) -> JudgeCritique:
    """Build a critique from a parsed model payload — the model proposes
    violations; the engine renders the brief (the model never hands us one)."""
    raw_violations = data.get("violations", []) or []
    violations: list[JudgeViolation] = []
    for item in raw_violations:
        if not isinstance(item, dict):
            continue
        axis = item.get("axis")
        severity = item.get("severity")
        if axis in ("beat", "voice", "tragedy") and severity in ("soft", "hard"):
            violations.append(JudgeViolation(
                axis=axis, severity=severity, detail=str(item.get("detail", "")),
            ))
    return JudgeCritique(
        verdict=_verdict(violations),
        beat_score=float(data.get("beat_score", 1.0)),
        voice_score=float(data.get("voice_score", 1.0)),
        tragedy_score=float(data.get("tragedy_score", 1.0)),
        violations=violations,
        critique_brief=render_brief(violations),  # engine-rendered, never model text
    )


class Sophia(AgentBase):
    name = "sophia"

    async def evaluate(self, state: ThreadState, action: str) -> JudgeCritique:
        """AgentBase contract stub — Sophia's real entry point is judge()."""
        return JudgeCritique()

    async def judge(self, prose: str, ctx: "TurnContext") -> JudgeCritique:
        """Score Clotho's render. Returns a critique; writes no state."""
        facts = _extract_facts(ctx)
        model = settings.sophia_model

        if model == "mock":
            await mock_pause(0.15)
            # Judge the deterministic state-derived substrate, hard checks only,
            # so grounded grim play passes hermetically (ADJ-E1).
            substrate = _mock_repair_prose(ctx.outcome.state, ctx.scene_outcome)
            return _critique_from_text(substrate, facts, include_soft=False)

        authored = _clotho_authored(prose)
        for attempt in range(2):  # one call + one informed retry (Morpheus pattern)
            try:
                raw = await llm.generate(
                    model=model,
                    system_prompt=SOPHIA_SYSTEM_PROMPT,
                    user_message=_build_payload(authored, facts),
                    temperature=0.2,
                    max_tokens=400,
                    json_mode=("anthropic" not in model),
                )
                if raw and raw.strip():
                    return _critique_from_payload(_parse_payload(raw))
            except Exception as exc:
                logger.warning(f"Sophia judge attempt {attempt + 1} failed: {exc!r}")
        # Fail-open: an optional organ never blocks the turn (ADJ-E6).
        return JudgeCritique(verdict="pass", judged=False)


def _build_payload(prose: str, facts: _Facts) -> str:
    return json.dumps({
        "prose": prose,
        "beat_position": facts.beat_position,
        "present_npcs": list(facts.present_npcs),
        "immediate_problem": facts.immediate_problem,
        "life_voice": facts.life_voice,
        "last_outcome": facts.last_outcome,
        "world_state_is_dangerous": facts.pressure_active,
    })
