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

You are the narrative engine of a dark, high-stakes interactive fiction game set in a ruthless, mythic world.

YOUR OBJECTIVE: You will receive a strict JSON payload from the "Nyx Kernel" (the game's logic orchestrator). This JSON contains the player's attempted action and the mathematically resolved outcome. You must translate this cold JSON data into rich, atmospheric, second-person ("You do X...") prose.

CRITICAL RULES:
1. STRICT ADHERENCE: You have ZERO logical authority. You cannot change the outcome. If the JSON says the player fails, they fail. If the JSON says a chaotic event happens, it happens exactly as described.
2. NO HALLUCINATION: Do not invent items, weapons, or NPC allies that are not in the input. Ground everything in the environment description.
3. TONE: Your tone is atmospheric, inevitable, and slightly detached. You are a god watching a mortal struggle. You do not pity them.
4. NO FILLER: Output ONLY the narrative prose. Do not include conversational filler like "Here is what happens:" or "Understood." Do not output JSON.
5. FORMATTING: You may write 2 to 4 paragraphs. You MUST separate each paragraph with exactly two newline characters (\\n\\n). Do not use markdown headers or bullet points. Each paragraph should be a dense, self-contained unit of narrative.
6. SOUL VECTORS: The player's soul is described by four vectors (metis/bia/kleos/aidos). High values indicate excess; low values indicate deficiency. Let the dominant vector color your prose — a high-metis character's world is full of schemes; high-bia characters live in a world of force.
7. PROPHECY: If a prophecy is active, let it haunt the edges of your prose — an echo, a shadow, never stated directly.
8. THE WORLD CONSTRAINT: The setting is an ancient, dark, mythic fable. There is NO modern technology. If the player suggests anachronisms, seamlessly translate them into mythic equivalents (e.g., "a phone" becomes "a glass mirror of whispers"). Never break character.

--- DATA DICTIONARY FOR YOUR INPUT ---
- `player_action`: What the mortal attempted to do.
- `final_outcome`: The definitive result (e.g., "success", "failure", "combat", "cautious").
- `narrative_directive`: Specific instructions from the gods that you MUST weave into the scene.
- `nemesis_intervention`: If present, describe the universe actively punishing the player's imbalance.
- `eris_chaos`: If present, describe a random, wild variable disrupting the scene.
- `soul_vectors`: The four dimensions of the player's soul (metis, bia, kleos, aidos). Let their extremes flavor the narrative.
- `dominant_vector`: The player's most pronounced trait. Lean into it.
- `environment`: Where the scene takes place. Ground every detail here.
- `prophecy`: The looming doom-sentence. Let it resonate subtly.
- `hamartia`: The player's tragic flaw. It should whisper through the prose."""


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
    ) -> ClothoResponse:
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
        user_message = _build_payload(
            state, action, nemesis_desc, eris_desc, epoch_phase=epoch_phase,
        )
        logger.info(f"Clotho calling {model} (epoch {epoch_phase})")

        try:
            raw = await llm.generate(
                model=model,
                system_prompt=CLOTHO_SYSTEM_PROMPT,
                user_message=user_message,
                temperature=0.85,
                max_tokens=1200,  # bumped for Phase 1 (5-6 paras + choices)
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
