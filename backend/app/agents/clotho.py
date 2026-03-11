"""Clotho - The Weaver / Generative Prose v3.0 (Epoch-Aware).

'You are Clotho. Your function is narrative generation. When pinged
with a consensus JSON, produce immersive, rich world-building prose
based on the resolved state. Do not concern yourself with player
survival or logic; weave the outcome beautifully.'

v3.0 changes:
- Epoch-aware paragraph counts + choice generation
- ---CHOICES--- separator for LLM output parsing
- Fallback choices per epoch phase
- max_tokens bumped 600 → 1200 for Phase 1 (5-6 paragraphs + choices)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import AsyncGenerator

from app.agents.base import AgentBase
from app.core.config import settings
from app.schemas.state import ClothoResponse, ThreadState
from app.services import llm
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.clotho")


# ---------------------------------------------------------------------------
# System Prompt (The Sandwich Method)
# ---------------------------------------------------------------------------

CLOTHO_SYSTEM_PROMPT = """You are Clotho, the Primordial Weaver of Fates.

═══════════════════════════════════════════
THE LAWS OF THE LOOM (inviolable)
═══════════════════════════════════════════

LAW I — THE ICEBERG PRINCIPLE
Never name an emotion. Never write "he felt afraid" or "she was angry."
Instead, describe a PHYSICAL OBJECT or SENSATION that reflects the emotion.
Fear is a dry mouth. Rage is a hand that will not unclench. Grief is
the smell of a room after someone has left it.
The reader must feel it in their body, not read it with their mind.

LAW II — THE KINETIC CONSTRAINT
Strike all passive "to be" verbs from your prose. No "was," "were,"
"is," "are," "been." The world ACTS. Rewrite every sentence so that
a concrete subject performs a concrete verb.
BAD:  "The room was dark."
GOOD: "Darkness swallowed the room."

LAW III — THE SENSE SUPREMACY
Every response must weave in exactly THREE sensory anchors:
  • One SMELL (smoke, wet stone, copper, pine resin, rot)
  • One TEXTURE (rough wool, cold iron, cracked earth, slick blood)
  • One SOUND (dripping water, distant drums, a blade leaving its sheath)
These are not decorations. They are the skeleton of reality.

LAW IV — THE ANCIENT GUARDRAIL
The setting is a pre-technological mythic fable. There is NO modern
technology. If the player suggests anachronisms, seamlessly translate
them into mythic equivalents ("a phone" → "a glass mirror of whispers").
Never break the world.

LAW V — THE ANCHOR (PLOT & IDENTITY)
Ambience is useless without context. You MUST clearly establish the
reality of the player's world. Who is raising them? What is their
social standing? What is the immediate, tangible situation occurring
right now? Every scene must answer: WHERE am I, WHO is with me,
and WHAT is happening? Atmosphere without grounding is fog.

LAW VI — ECONOMY OF BREATH
Do not exhaust the player. For standard turns, output a maximum of
2 to 3 concise paragraphs. Only expand to longer descriptions during
major life events or Epoch transitions. Dense prose beats long prose.

═══════════════════════════════════════════
YOUR FUNCTION
═══════════════════════════════════════════

You will receive a JSON payload from the Nyx Kernel containing the
player's action and the mathematically resolved outcome. Translate
this data into second-person ("You do X...") literary prose.

RULES OF ENGAGEMENT:
1. ZERO AUTHORITY: You cannot change outcomes. If the JSON says failure, weave failure.
2. NO HALLUCINATION: Do not invent items, allies, or locations absent from the input.
3. TONE: Atmospheric, inevitable, slightly detached. A god watching a mortal struggle.
4. NO FILLER: Output ONLY prose. No "Here is what happens:" — no JSON, no markdown.
5. FORMAT: Separate paragraphs with two newlines. Dense, self-contained units.
6. PROPHECY: If active, let it haunt the margins — an echo, never stated directly.

--- DATA DICTIONARY ---
- `player_action`: What the mortal attempted.
- `final_outcome`: The resolved result.
- `narrative_directive`: Instructions from the gods you MUST honor.
- `nemesis_intervention`: Universe punishing the player's imbalance.
- `eris_chaos`: A wild variable disrupting the scene.
- `soul_vectors`: Four soul dimensions (metis/bia/kleos/aidos).
- `dominant_vector`: The loudest trait. Lean into it.
- `environment`: Where the scene lives. Ground every detail.
- `prophecy`: The doom-sentence. Let it resonate.
- `hamartia`: The tragic flaw whispering through the prose."""


# ---------------------------------------------------------------------------
# Mock Prose (Phase 1 fallback)
# ---------------------------------------------------------------------------

_OPENERS = [
    "The air shifts around you.",
    "Silence stretches, then breaks.",
    "The world holds its breath for a moment.",
    "Shadows lengthen as your choice takes shape.",
    "Something fundamental changes in the fabric of this place.",
]

_PROSE_POOLS = {
    "birth": [
        "You open your eyes for the first time and the world is enormous. "
        "Firelight dances on rough stone walls. Somewhere, a woman hums a melody "
        "that you will forget by morning but carry in your bones forever.\n\n"
        "Small hands. Small fingers. You curl them around a thread of wool "
        "and pull, and the whole world seems to tremble at the gesture. "
        "Outside, the wind speaks a language older than names.",
        "The first thing you know is warmth. Then cold. Then the ache "
        "between the two — a lesson the world will teach you again and again.\n\n"
        "You are three years old, and the hearthfire paints shadows on the ceiling "
        "that move like living things. One of them watches you back. "
        "You do not cry. You have already learned that crying changes nothing.",
        "Smoke and animal fat. The smell of the world before you had words for it. "
        "You sit in the dirt outside a dwelling that leans against the hillside "
        "like a wounded creature.\n\n"
        "A dog noses your hand. You grab its ear and it lets you, patient "
        "as stone. Above, the sky is the color of old iron, and somewhere "
        "in the distance, the Fates are threading their loom.",
    ],
    "combat": [
        "Steel meets resistance. The clash echoes through stone corridors, "
        "a violent prayer to gods who do not answer.",
        "You move with desperate purpose. Blood — yours or theirs — "
        "paints the ground in dark scripture.",
        "The fight is ugly, honest. No glory, only survival measured "
        "in heartbeats and inches.",
    ],
    "cunning_success": [
        "Your words weave a web the fool never sees. The thread of deceit "
        "pulls taut, and the world rearranges itself to your design.",
        "Cleverness is its own kind of violence. You dismantle their certainty "
        "with a smile they will never forgive.",
    ],
    "glory_success": [
        "The world watches. You feel the weight of a thousand unseen eyes "
        "as your name carves itself into the air.",
        "Fame is a hunger. You feed it, and it grows, and the Fates "
        "take note of one who burns so bright.",
    ],
    "cautious": [
        "You pull back from the edge. Wisdom, or cowardice — "
        "the distinction matters less than survival.",
        "In stillness, you find a fragile peace. The world "
        "continues its slow entropy around you.",
        "Rest comes, but not comfort. Even in safety, the thread "
        "of your story pulls taut.",
    ],
    "neutral": [
        "You move through the world, leaving barely a ripple. "
        "The Fates watch, but do not yet intervene.",
        "Another step along an unmarked path. The story writes "
        "itself in your footprints.",
        "Nothing changes, and yet everything feels different. "
        "The weight of potential hangs heavy.",
    ],
}


def _mock_prose(state: ThreadState) -> str:
    outcome = state.last_outcome or "neutral"
    pool = _PROSE_POOLS.get(outcome, _PROSE_POOLS["neutral"])
    body = random.choice(pool)
    # Birth prose is self-contained (multi-paragraph); skip the generic opener
    if outcome == "birth":
        return body
    return f"{random.choice(_OPENERS)}\n\n{body}"


# ---------------------------------------------------------------------------
# Epoch Directives & Fallback Choices
# ---------------------------------------------------------------------------

EPOCH_DIRECTIVES = {
    1: (
        "EPOCH PHASE 1 (Age 3-6): Write 5 to 6 paragraphs of childlike wonder. "
        "Simple language, sensory details. After your prose, output exactly 3 choices."
    ),
    2: (
        "EPOCH PHASE 2 (Age 7-11): Write 4 to 5 paragraphs. Growing vocabulary, "
        "testing boundaries. After your prose, output 4 to 5 choices."
    ),
    3: (
        "EPOCH PHASE 3 (Age 12-16): Write 2 to 3 paragraphs. Terse, intense. "
        "After your prose, output 5 to 6 morally ambiguous choices."
    ),
    4: (
        "EPOCH PHASE 4 (Age 18+): Write exactly 1 dense paragraph. "
        "No choices — the player types freely. Do NOT output any choices section."
    ),
}

_FALLBACK_CHOICES: dict[int, list[str]] = {
    1: ["Look around carefully", "Cry for help", "Hide in the shadows"],
    2: ["Investigate further", "Talk to someone nearby", "Search for supplies", "Retreat to safety"],
    3: ["Strike first", "Set a trap", "Negotiate terms", "Observe from hiding", "Rally allies"],
    4: [],
}


# ---------------------------------------------------------------------------
# Choice Parser
# ---------------------------------------------------------------------------

def _parse_clotho_output(raw: str, epoch_phase: int) -> tuple[str, list[str]]:
    """Split Clotho output on ---CHOICES--- separator.

    Returns (prose, choices). Falls back to deterministic choices on failure.
    Phase 4 always returns empty choices.
    """
    if epoch_phase >= 4:
        return raw.strip(), []

    separator = "---CHOICES---"
    if separator in raw:
        parts = raw.split(separator, 1)
        prose = parts[0].strip()
        choices_raw = parts[1].strip()
        try:
            choices = json.loads(choices_raw)
            if isinstance(choices, list) and all(isinstance(c, str) for c in choices):
                return prose, choices
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Clotho choice parse failed: {choices_raw[:100]}")

    # Fallback: return prose as-is + deterministic choices
    logger.info(f"Using fallback choices for epoch {epoch_phase}")
    return raw.strip(), _FALLBACK_CHOICES.get(epoch_phase, [])


# ---------------------------------------------------------------------------
# Payload Builder
# ---------------------------------------------------------------------------

def _build_payload(
    state: ThreadState,
    action: str,
    nemesis_desc: str = "",
    eris_desc: str = "",
    epoch_phase: int = 1,
) -> str:
    """Build the structured JSON payload for Clotho's user message."""
    vectors = state.soul_ledger.vectors

    # Determine narrative directives from outcome + soul state
    directives: list[str] = []
    outcome = state.last_outcome or "neutral"

    if outcome == "combat":
        directives.append("Player engaged in combat. Describe the violence and stakes.")
    elif outcome in ("cunning_success", "acquisition"):
        directives.append("Player succeeded through cleverness. Describe the web they wove.")
    elif outcome == "cautious":
        directives.append("Player chose caution. Describe the tension of restraint.")

    # Soul-state flavor
    dominant = SoulVectorEngine.dominant_vector(vectors)
    imbalance = SoulVectorEngine.imbalance_score(vectors)
    if imbalance > 6.0:
        directives.append(
            f"The player's soul is dangerously imbalanced — {dominant} dominates. "
            "Let this excess color the world around them."
        )

    # Dead soul warning
    vals = list(vectors.model_dump().values())
    if all(v <= 2.0 for v in vals):
        directives.append("The player's soul is guttering. Fragility, exhaustion, fading light.")

    payload = {
        "player_action": action,
        "final_outcome": outcome,
        "narrative_directive": (
            " ".join(directives) if directives
            else "Standard scene. No special interventions."
        ),
        "nemesis_intervention": nemesis_desc or None,
        "eris_chaos": eris_desc or None,
        "soul_vectors": vectors.model_dump(),
        "dominant_vector": dominant,
        "environment": state.session.current_environment,
        "prophecy": state.the_loom.current_prophecy or None,
        "hamartia": state.soul_ledger.hamartia or None,
        "turn_number": state.session.turn_count,
        "player_name": state.session.player_name,
        "player_gender": state.session.player_gender,
    }

    msg = "WEAVE THE FOLLOWING STATE INTO REALITY:\n\n" + json.dumps(payload, indent=2)

    # Append player identity directive (before epoch)
    if state.session.player_name != "Stranger":
        msg += (
            f"\n\n--- PLAYER IDENTITY ---\n"
            f"The player's name is {state.session.player_name}. "
            f"They are a {state.session.player_gender}. "
            f"Use appropriate pronouns. Weave the name sparingly."
        )

    # Append epoch directive
    directive = EPOCH_DIRECTIVES.get(epoch_phase, EPOCH_DIRECTIVES[4])
    msg += f"\n\n--- EPOCH INSTRUCTIONS ---\n{directive}"

    # Append choice format instructions (Phase 1-3 only)
    if epoch_phase < 4:
        msg += (
            "\n\nAFTER your prose paragraphs, output the following on a new line:\n"
            "---CHOICES---\n"
            'Then output a JSON array of choice strings. Example:\n'
            '["Run toward the light", "Hide in the darkness", "Call out to the voice"]\n'
            "Output ONLY the prose paragraphs, then the separator, then the JSON array. Nothing else."
        )

    return msg


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Clotho(AgentBase):
    name = "clotho"

    async def evaluate(
        self, state: ThreadState, action: str,
        nemesis_desc: str = "",
        eris_desc: str = "",
        epoch_phase: int = 1,
        stratified_context: str = "",
    ) -> ClothoResponse:
        """Generate literary prose from resolved state.

        Args:
            stratified_context: If provided, this pre-assembled context string
                is PREPENDED to the system prompt. Contains [Literary Laws] +
                [Chronicle] + [Soul Mirror] + [Last 2 Turns]. Built by the
                kernel's Stratified Context Builder.
        """
        model = settings.clotho_model

        # --- Mock mode ---
        if model == "mock":
            await asyncio.sleep(0.5)
            choices = _FALLBACK_CHOICES.get(epoch_phase, [])
            return ClothoResponse(
                prose=_mock_prose(state),
                scene_tags=[state.last_outcome or "neutral"],
                ui_choices=choices,
            )

        # --- Real LLM mode ---
        # Assemble system prompt: stratified context layers + base prompt
        system = CLOTHO_SYSTEM_PROMPT
        if stratified_context:
            system = stratified_context + "\n\n" + CLOTHO_SYSTEM_PROMPT

        user_message = _build_payload(
            state, action, nemesis_desc, eris_desc, epoch_phase=epoch_phase,
        )
        logger.info(f"Clotho calling {model} (epoch {epoch_phase}, context={len(stratified_context)} chars)")

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=system,
                user_message=user_message,
                temperature=0.85,
                max_tokens=1200,
            )
            logger.info(f"Clotho generated {len(raw)} chars")
            prose, choices = _parse_clotho_output(raw, epoch_phase)
            return ClothoResponse(
                prose=prose,
                scene_tags=[state.last_outcome or "neutral"],
                ui_choices=choices,
            )
        except Exception as e:
            logger.error(f"Clotho LLM failed: {e}. Falling back to mock.")
            choices = _FALLBACK_CHOICES.get(epoch_phase, [])
            return ClothoResponse(
                prose=_mock_prose(state),
                scene_tags=[state.last_outcome or "neutral"],
                ui_choices=choices,
            )

    async def astream(
        self, state: ThreadState, action: str,
        nemesis_desc: str = "",
        eris_desc: str = "",
        epoch_phase: int = 1,
        stratified_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream prose tokens for the SSE pipeline.

        Mock mode: chunks mock prose into 3-word groups with delays.
        Real LLM mode: delegates to llm.stream() for token-by-token output.

        IMPORTANT: This yields raw tokens including the ---CHOICES--- section.
        The kernel's stream handler is responsible for buffering and splitting
        the choices separator from the prose tokens.
        """
        model = settings.clotho_model

        # --- Mock mode: simulate token streaming ---
        if model == "mock":
            await asyncio.sleep(0.3)
            prose = _mock_prose(state)
            # Append mock choices separator for phases 1-3
            choices = _FALLBACK_CHOICES.get(epoch_phase, [])
            if epoch_phase < 4 and choices:
                prose += "\n\n---CHOICES---\n" + json.dumps(choices)

            words = prose.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i + 3])
                # Add leading space except for the first chunk
                if i > 0:
                    chunk = " " + chunk
                yield chunk
                await asyncio.sleep(random.uniform(0.04, 0.08))
            return

        # --- Real LLM mode: stream via LiteLLM ---
        system = CLOTHO_SYSTEM_PROMPT
        if stratified_context:
            system = stratified_context + "\n\n" + CLOTHO_SYSTEM_PROMPT

        user_message = _build_payload(
            state, action, nemesis_desc, eris_desc, epoch_phase=epoch_phase,
        )
        logger.info(f"Clotho streaming {model} (epoch {epoch_phase})")

        try:
            async for token in llm.stream(
                model=model,
                system_prompt=system,
                user_message=user_message,
                temperature=0.85,
                max_tokens=1200,
            ):
                yield token
        except Exception as e:
            logger.error(f"Clotho stream failed: {e}. Falling back to mock chunks.")
            prose = _mock_prose(state)
            words = prose.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i + 3])
                if i > 0:
                    chunk = " " + chunk
                yield chunk
                await asyncio.sleep(random.uniform(0.04, 0.08))
