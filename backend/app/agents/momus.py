"""Momus - The Validator and Repair Judge.

Momus performs two kinds of deterministic checks:

1. Hallucinations: contradictions against canonical thread state.
2. Literary law violations: stylistic problems that should be observed
   but do not make the prose false.

When factual drift is detected, Momus now emits a repair brief and a
safer fallback prose candidate so the kernel can retry Clotho once
before committing a turn.
"""

from __future__ import annotations

import asyncio
import re

from app.agents.base import AgentBase
from app.schemas.state import MomusValidation, ThreadState
from app.services.canon import render_scene_snapshot
from app.services.pressure import pressure_summary

_TERRAIN_PAIRS: list[tuple[str, str]] = [
    ("ocean", "desert"),
    ("sea", "desert"),
    ("forest", "ocean"),
    ("mountain", "underwater"),
    ("cave", "sky"),
    ("dungeon", "meadow"),
]

_ANACHRONISMS: set[str] = {
    "phone",
    "telephone",
    "cellphone",
    "smartphone",
    "email",
    "internet",
    "wifi",
    "website",
    "computer",
    "laptop",
    "tablet",
    "radio",
    "television",
    "tv",
    "broadcast",
    "car",
    "automobile",
    "truck",
    "bus",
    "train",
    "railroad",
    "airplane",
    "helicopter",
    "jet",
    "subway",
    "motorcycle",
    "gun",
    "pistol",
    "rifle",
    "bullet",
    "bomb",
    "grenade",
    "cannon",
    "missile",
    "rocket",
    "dynamite",
    "explosive",
    "electricity",
    "battery",
    "generator",
    "motor",
    "engine",
    "plastic",
    "nylon",
    "concrete",
    "asphalt",
    "semiconductor",
    "factory",
    "skyscraper",
    "elevator",
    "escalator",
    "robot",
    "machine",
    "microchip",
    "software",
    "hardware",
    "photograph",
    "camera",
    "video",
    "film",
    "cinema",
    "newspaper",
    "magazine",
    "clock",
    "wristwatch",
    "glasses",
    "spectacles",
    "binoculars",
    "telescope",
    "microscope",
    "democracy",
    "communism",
    "capitalism",
    "socialism",
}

_EMOTION_THRESHOLD = 3
_EMOTION_WORDS: list[str] = [
    "afraid",
    "angry",
    "anxious",
    "ashamed",
    "bitter",
    "cheerful",
    "confused",
    "content",
    "delighted",
    "depressed",
    "desperate",
    "disappointed",
    "disgusted",
    "embarrassed",
    "envious",
    "excited",
    "frightened",
    "frustrated",
    "furious",
    "grateful",
    "guilty",
    "happy",
    "heartbroken",
    "hopeful",
    "hopeless",
    "horrified",
    "humiliated",
    "impatient",
    "irritated",
    "jealous",
    "joyful",
    "lonely",
    "melancholy",
    "miserable",
    "nervous",
    "nostalgic",
    "overjoyed",
    "panicked",
    "peaceful",
    "proud",
    "regretful",
    "relieved",
    "resentful",
    "sad",
    "satisfied",
    "scared",
    "shocked",
    "sorrowful",
    "surprised",
    "terrified",
    "thrilled",
    "tormented",
    "troubled",
    "uneasy",
    "worried",
]
_EMOTION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:felt|feeling|feels|was|were|is|are|seemed|appeared|looked|became|grew)\s+"
    + r"(?:" + "|".join(re.escape(e) for e in _EMOTION_WORDS) + r")\b",
    re.IGNORECASE,
)

_PASSIVE_PATTERN: re.Pattern[str] = re.compile(r"\b(?:was|were|is|are|been)\b", re.IGNORECASE)
_PASSIVE_THRESHOLD = 6
_PARAGRAPH_LIMIT = 5

_TITLE_ENTITY_PATTERN: re.Pattern[str] = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
)
_ENTITY_STOPWORDS = {
    "A",
    "An",
    "And",
    "Before",
    "But",
    "He",
    "Her",
    "His",
    "I",
    "If",
    "In",
    "It",
    "Its",
    "She",
    "The",
    "Their",
    "Then",
    "They",
    "This",
    "Those",
    "We",
    "When",
    "You",
    "Your",
}
_SCENE_ACTION_MARKERS = (
    " says",
    " said",
    " stands",
    " stood",
    " watches",
    " watched",
    " looks",
    " looked",
    " grabs",
    " grabbed",
    " touches",
    " touched",
    " steps",
    " stepped",
    " waits",
    " waited",
    " calls",
    " called",
    " enters",
    " entered",
    " kneels",
    " knelt",
    " offers",
    " offered",
    " smiles",
    " smiled",
    " frowns",
    " frowned",
    " reaches",
    " reached",
    " turns",
    " turned",
    " is here",
    " was here",
    "\"",
)
_ACTIVE_OATH_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:your oath|your vow|your promise|what you have sworn|sworn duty)\b",
    re.IGNORECASE,
)
_BROKEN_OATH_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:broken oath|oath is broken|broke your oath|forsworn|shattered vow)\b",
    re.IGNORECASE,
)
_FULFILLED_OATH_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:fulfilled oath|oath is fulfilled|kept your oath|vow fulfilled|promise kept)\b",
    re.IGNORECASE,
)

_PRESSURE_CONTRADICTIONS: dict[str, tuple[float, tuple[str, ...], str]] = {
    "suspicion": (
        1.5,
        (r"\bno one saw\b", r"\bnobody noticed\b", r"\bunwatched\b", r"\balone\b"),
        "Suspicion is high: witnesses or whispers should remain in play.",
    ),
    "scarcity": (
        1.5,
        (r"\babundance\b", r"\bplenty\b", r"\bwell-stocked\b", r"\bfull belly\b"),
        "Scarcity is active: do not describe easy plenty or comfort.",
    ),
    "wounds": (
        1.5,
        (r"\bunhurt\b", r"\bunwounded\b", r"\bwithout pain\b", r"\bwhole again\b"),
        "Wounds are active: the body should still carry damage.",
    ),
    "debt": (
        1.5,
        (r"\bowe nothing\b", r"\bdebts are paid\b", r"\bnothing owed\b"),
        "Debt is active: someone or something is still owed.",
    ),
    "faction_heat": (
        1.5,
        (r"\bno one hunts\b", r"\bauthority forgot\b", r"\bforgotten by the law\b"),
        "Faction heat is active: organized power has not let go.",
    ),
    "omen": (
        1.5,
        (r"\bno omen\b", r"\bfate is silent\b", r"\bthe gods are quiet\b"),
        "Omen pressure is active: fate should still feel near.",
    ),
}


class Momus(AgentBase):
    name = "momus"

    async def evaluate(self, state: ThreadState, action: str) -> MomusValidation:
        await asyncio.sleep(0.05)
        return MomusValidation(valid=True)

    async def validate_prose(self, prose: str, state: ThreadState) -> MomusValidation:
        """Check prose for factual drift and literary law violations."""
        await asyncio.sleep(0.1)

        hallucinations: list[str] = []
        law_violations: list[str] = []
        repair_notes: list[str] = []
        unsafe_fragments: list[str] = []
        prose_lower = prose.lower()

        named_entities = _extract_named_entities(prose)
        canon_hallucinations, canon_notes, canon_fragments = _check_canon_drift(
            prose, state, named_entities
        )
        hallucinations.extend(canon_hallucinations)
        repair_notes.extend(canon_notes)
        unsafe_fragments.extend(canon_fragments)

        env_lower = state.session.current_environment.lower()
        for a, b in _TERRAIN_PAIRS:
            if a in env_lower and b in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{b}' but environment is '{a}'-related."
                )
                repair_notes.append(
                    f"Keep terrain grounded in the current scene; remove the stray {b} imagery."
                )
                unsafe_fragments.append(b)
            elif b in env_lower and a in prose_lower:
                hallucinations.append(
                    f"Prose mentions '{a}' but environment is '{b}'-related."
                )
                repair_notes.append(
                    f"Keep terrain grounded in the current scene; remove the stray {a} imagery."
                )
                unsafe_fragments.append(a)

        active_oaths = [
            oath for oath in state.soul_ledger.active_oaths if oath.status == "active"
        ]
        broken_oaths = [
            oath for oath in state.soul_ledger.active_oaths if oath.status == "broken"
        ]
        fulfilled_oaths = [
            oath for oath in state.soul_ledger.active_oaths if oath.status == "fulfilled"
        ]

        if re.search(r"\b(oath|sworn|vow|promise)\b", prose_lower):
            if not state.soul_ledger.active_oaths:
                hallucinations.append(
                    "Prose references oaths or vows but no oath exists in state."
                )
                repair_notes.append("Remove oath language; the thread has no sworn obligation yet.")
                unsafe_fragments.extend(["oath", "vow", "promise", "sworn"])
            elif not active_oaths and _ACTIVE_OATH_PATTERN.search(prose_lower):
                hallucinations.append(
                    "Prose treats an oath as actively binding, but no oath is active."
                )
                repair_notes.append(
                    "Do not present an oath as currently binding unless one is active."
                )
                unsafe_fragments.extend(["your oath", "your vow", "your promise"])

        if _BROKEN_OATH_PATTERN.search(prose_lower) and not broken_oaths:
            hallucinations.append(
                "Prose says an oath is broken, but no oath is broken in state."
            )
            repair_notes.append("Do not describe a broken oath unless Nemesis has made it true.")
            unsafe_fragments.append("broken oath")

        if _FULFILLED_OATH_PATTERN.search(prose_lower) and not fulfilled_oaths:
            hallucinations.append(
                "Prose says an oath is fulfilled, but no oath is fulfilled in state."
            )
            repair_notes.append("Do not claim an oath is fulfilled before state confirms it.")
            unsafe_fragments.append("fulfilled oath")

        death_words = re.findall(
            r"\b(you die|you are dead|your life ends|you perish)\b", prose_lower
        )
        if death_words:
            vals = list(state.soul_ledger.vectors.model_dump().values())
            if any(v > 3.0 for v in vals):
                hallucinations.append(
                    "Prose declares player death but the soul has not collapsed."
                )
                repair_notes.append("Keep the player alive unless Atropos or the soul state makes death true.")
                unsafe_fragments.extend(death_words)

        pressure_hallucinations, pressure_notes, pressure_fragments = _check_pressure_drift(
            prose_lower, state
        )
        hallucinations.extend(pressure_hallucinations)
        repair_notes.extend(pressure_notes)
        unsafe_fragments.extend(pressure_fragments)

        found_anachronisms = _detect_anachronisms(prose_lower)
        if found_anachronisms:
            law_violations.append(
                "Law IV (Ancient Guardrail): anachronism detected - "
                + ", ".join(sorted(found_anachronisms))
                + "."
            )

        emotion_matches = _EMOTION_PATTERN.findall(prose)
        if len(emotion_matches) > _EMOTION_THRESHOLD:
            law_violations.append(
                "Law I (Show Then Tell): excessive emotion naming - "
                f"found {len(emotion_matches)} instance(s) (threshold: {_EMOTION_THRESHOLD})."
            )

        passive_count = len(_PASSIVE_PATTERN.findall(prose))
        if passive_count > _PASSIVE_THRESHOLD:
            law_violations.append(
                f"Law II (Player Acts): {passive_count} passive 'to be' verbs "
                f"(threshold: {_PASSIVE_THRESHOLD})."
            )

        paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
        if len(paragraphs) > _PARAGRAPH_LIMIT:
            law_violations.append(
                f"Law VI (Economy of Breath): {len(paragraphs)} paragraphs "
                f"(limit: {_PARAGRAPH_LIMIT})."
            )

        repair_needed = len(hallucinations) > 0
        corrected = prose
        repair_brief = ""
        if repair_needed:
            corrected = _build_safe_prose(prose, state, unsafe_fragments)
            repair_brief = _build_repair_brief(state, repair_notes or hallucinations)

        return MomusValidation(
            valid=not repair_needed,
            hallucinations=hallucinations,
            law_violations=law_violations,
            repair_needed=repair_needed,
            repair_brief=repair_brief,
            corrected_prose=corrected,
        )


def _extract_named_entities(prose: str) -> set[str]:
    """Return a small deterministic set of title-case entities from prose."""
    entities: set[str] = set()
    for match in _TITLE_ENTITY_PATTERN.findall(prose):
        if match in _ENTITY_STOPWORDS:
            continue
        entities.add(match)
    return entities


def _split_sentences(prose: str) -> list[str]:
    """Split prose into sentence-like spans for redaction."""
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", prose) if part.strip()]


def _mentions_scene_participation(sentence: str) -> bool:
    """Return True when a sentence treats an entity as physically present now."""
    lowered = f" {sentence.lower()} "
    return any(marker in lowered for marker in _SCENE_ACTION_MARKERS)


def _check_canon_drift(
    prose: str,
    state: ThreadState,
    named_entities: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Compare title-case and known names against canonical scene truth."""
    canon = state.canon
    if not canon or not canon.current_scene:
        return [], [], []

    hallucinations: list[str] = []
    repair_notes: list[str] = []
    unsafe_fragments: list[str] = []
    prose_lower = prose.lower()
    scene = canon.current_scene
    present_ids = set(scene.present_npc_ids)
    current_location = canon.locations.get(scene.location_id)
    sentences = _split_sentences(prose)

    if current_location is not None:
        for location in canon.locations.values():
            if location.location_id == scene.location_id:
                continue
            if location.name.lower() in prose_lower:
                hallucinations.append(
                    f"Prose relocates the scene to '{location.name}', but canon says '{current_location.name}'."
                )
                repair_notes.append(
                    f"Keep the scene in {current_location.name}; do not move it to {location.name}."
                )
                unsafe_fragments.append(location.name)

    known_names = {npc.name for npc in canon.npcs.values()}
    for entity in named_entities.intersection(known_names):
        npc = next((candidate for candidate in canon.npcs.values() if candidate.name == entity), None)
        if npc is None:
            continue
        entity_sentences = [
            sentence for sentence in sentences if entity.lower() in sentence.lower()
        ]
        if not entity_sentences:
            continue
        participates = any(_mentions_scene_participation(sentence) for sentence in entity_sentences)
        if npc.status == "dead" and participates:
            hallucinations.append(
                f"Prose treats {npc.name} as present, but canon marks them dead."
            )
            repair_notes.append(f"Do not place {npc.name} in the scene; they are dead in canon.")
            unsafe_fragments.append(npc.name)
        elif npc.npc_id not in present_ids and participates:
            hallucinations.append(
                f"Prose puts {npc.name} in the current scene, but they are not present."
            )
            repair_notes.append(
                f"Only the scene's present NPCs may participate directly; remove {npc.name} from the scene."
            )
            unsafe_fragments.append(npc.name)

    return hallucinations, repair_notes, unsafe_fragments


def _check_pressure_drift(
    prose_lower: str,
    state: ThreadState,
) -> tuple[list[str], list[str], list[str]]:
    """Catch prose that denies the most active pressures."""
    hallucinations: list[str] = []
    repair_notes: list[str] = []
    unsafe_fragments: list[str] = []

    for key, (threshold, patterns, correction) in _PRESSURE_CONTRADICTIONS.items():
        value = getattr(state.pressures, key, 0.0)
        if value < threshold:
            continue
        for pattern in patterns:
            match = re.search(pattern, prose_lower)
            if match is None:
                continue
            hallucinations.append(
                f"Prose denies active pressure '{key}' even though it is elevated in state."
            )
            repair_notes.append(correction)
            unsafe_fragments.append(match.group(0))
            break

    return hallucinations, repair_notes, unsafe_fragments


def _build_safe_prose(prose: str, state: ThreadState, unsafe_fragments: list[str]) -> str:
    """Return a conservative fallback by removing contradictory sentences."""
    fragments = {fragment.lower() for fragment in unsafe_fragments if fragment}
    kept: list[str] = []
    for sentence in _split_sentences(prose):
        lowered = sentence.lower()
        if any(fragment in lowered for fragment in fragments):
            continue
        kept.append(sentence)

    candidate = " ".join(kept).strip()
    if candidate and candidate != prose.strip():
        return candidate
    return _scene_fallback_prose(state)


def _scene_fallback_prose(state: ThreadState) -> str:
    """Build a minimal safe description from canon and pressure state."""
    canon = state.canon
    if canon and canon.current_scene:
        scene = canon.current_scene
        location = canon.locations.get(scene.location_id)
        present = [
            canon.npcs[npc_id].name
            for npc_id in scene.present_npc_ids
            if npc_id in canon.npcs and canon.npcs[npc_id].status == "alive"
        ]
        lines: list[str] = []
        if location is not None:
            lines.append(f"You remain in {location.name}.")
        if scene.immediate_problem:
            lines.append(scene.immediate_problem.rstrip(".") + ".")
        if present:
            lines.append(", ".join(present) + " remain within reach.")
        pressure_line = pressure_summary(state)
        if pressure_line and not pressure_line.startswith("No external pressure"):
            lines.append(f"The world still presses close: {pressure_line}.")
        if lines:
            return "\n\n".join(lines)

    snapshot = render_scene_snapshot(state)
    if snapshot:
        return snapshot
    return state.session.current_environment or "The scene refuses to break canon, but words fail it."


def _build_repair_brief(state: ThreadState, repair_notes: list[str]) -> str:
    """Render a concise retry brief for Clotho."""
    lines = [
        "Rewrite the scene so it obeys canon exactly while preserving the same dramatic intent.",
        "Fix these contradictions:",
    ]
    for note in repair_notes[:6]:
        lines.append(f"- {note}")

    snapshot = render_scene_snapshot(state)
    if snapshot:
        lines.append("Canon snapshot:")
        lines.append(snapshot)

    active_oaths = [
        oath for oath in state.soul_ledger.active_oaths if oath.status == "active"
    ]
    if active_oaths:
        oath_text = "; ".join(oath.text for oath in active_oaths[:2])
        lines.append(f"Active oaths that may be referenced: {oath_text}")
    else:
        lines.append("There is no active oath unless the state explicitly says otherwise.")

    pressure_line = pressure_summary(state)
    if pressure_line:
        lines.append(f"Pressure truth: {pressure_line}")

    lines.append("Output fresh prose, not an explanation.")
    return "\n".join(lines)


def _detect_anachronisms(prose_lower: str) -> set[str]:
    """Return the set of anachronistic words found in prose."""
    found: set[str] = set()
    for word in _ANACHRONISMS:
        if re.search(rf"\b{re.escape(word)}\b", prose_lower):
            found.add(word)
    return found
