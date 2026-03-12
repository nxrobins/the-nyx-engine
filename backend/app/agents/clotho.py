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
from app.services.prompt_loader import load_prompt
from app.services.soul_math import SoulVectorEngine

logger = logging.getLogger("nyx.clotho")


# ---------------------------------------------------------------------------
# System Prompt (loaded from app/prompts/clotho.yaml)
# ---------------------------------------------------------------------------

CLOTHO_SYSTEM_PROMPT = load_prompt("clotho")


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

_VOICE_DIRECTIVES: dict[int, str] = {
    1: (
        "VOICE — EARLY CHILDHOOD: "
        "Short, concrete sentences. The child sees and feels but does not analyze. "
        "Adults are big, voices are loud or quiet, food is good or bad. "
        "Use words a small child would know. Adults' dialogue should be "
        "half-understood: the child catches tone and fragments, not meaning. "
        "Write 4-5 paragraphs. After your prose, output exactly 3 choices."
    ),
    2: (
        "VOICE — MIDDLE CHILDHOOD: "
        "The child reasons in concretes. Fairness is the highest value. "
        "Social hierarchy is physical: who sits where, who eats first, who gets hit. "
        "Dialogue is understood but adult motives are misread. "
        "Internal thoughts are forming: 'That isn't right' and 'I have to be careful.' "
        "Write 3-4 paragraphs. After your prose, output 4-5 choices."
    ),
    3: (
        "VOICE — ADOLESCENCE: "
        "Full vocabulary. Self-conscious. The body is a problem. "
        "Emotions run hot and contradictory. Bravado masks fear. "
        "Sees hypocrisy everywhere, overreacts to everything. "
        "Dialogue is sharp, defensive, sometimes cruel. "
        "Write 2-3 paragraphs. After your prose, output 5-6 morally ambiguous choices."
    ),
    4: (
        "VOICE — ADULTHOOD: "
        "Full register. Terse. Every scene carries the weight of "
        "accumulated choices. Actions have history behind them. "
        "Write 1-2 dense paragraphs. No choices — the player types freely."
    ),
}

_FALLBACK_CHOICES: dict[int, list[str]] = {
    1: [  # Bia / Metis / Aidos
        "Push them away",
        "Pretend you didn't see anything",
        "Hide behind your mother",
    ],
    2: [  # Bia / Metis / Aidos / Kleos
        "Shove your way through",
        "Tell a lie to get what you want",
        "Slip away quietly",
        "Stand up and say something loud",
    ],
    3: [  # Bia / Metis / Aidos / Kleos / Wild
        "Hit first and hard",
        "Find their weakness and use it",
        "Walk away before it gets worse",
        "Challenge them in front of everyone",
        "Do something nobody expects",
    ],
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
    vignette_directive: str = "",
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
        "player_age": state.session.player_age,
        "beat_position": state.session.beat_position,
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

    # Voice register + age pinning (Sprint 8: The Director)
    voice = _VOICE_DIRECTIVES.get(epoch_phase, _VOICE_DIRECTIVES[4])
    msg += f"\n\n--- VOICE & AGE ---\n{voice}"
    msg += (
        f"\nThe player is EXACTLY {state.session.player_age} years old. "
        "Pin all sensory details, vocabulary, and world-knowledge to this age. Do NOT drift."
    )

    # Beat / vignette directive (epochs 1-3)
    if vignette_directive:
        msg += f"\n\n--- SCENE BEAT ({state.session.beat_position}) ---\n{vignette_directive}"

    # Append vector-mapped choice instructions (Phase 1-3 only)
    if epoch_phase < 4:
        choice_count = {1: 3, 2: 4, 3: 5}.get(epoch_phase, 3)
        msg += (
            f"\n\n--- CHOICES ---\n"
            f"After your prose, output exactly {choice_count} choices.\n"
            f"CHOICE RULES:\n"
            f"- Each choice is a PHYSICAL ACTION the character can take RIGHT NOW\n"
            f"- Use concrete verbs: run, grab, say, hide, throw, follow, refuse, lie\n"
            f"- NEVER use philosophical gestures: 'embrace the shadow', 'accept fate'\n"
            f"- Map choices to soul vectors:\n"
            f"  • One FORCEFUL option (Bia): fight, break, intimidate, confront\n"
            f"  • One CLEVER option (Metis): trick, persuade, steal, outmaneuver\n"
            f"  • One CAUTIOUS option (Aidos): hide, wait, retreat, observe, show mercy\n"
        )
        # Phase 2+ gets a 4th choice; Phase 3 gets a 5th
        if epoch_phase >= 2:
            msg += f"  • One BOLD/PUBLIC option (Kleos): declare, challenge, volunteer, stand up\n"
        if epoch_phase >= 3:
            msg += f"  • One WILD option: an unexpected action that doesn't fit the other categories\n"
        msg += (
            f"- Choices should lead to DIFFERENT outcomes, not different moods\n"
            f"- At least one choice should involve speaking to someone present\n"
            f"- Format: ---CHOICES--- then a JSON array\n"
            f'Example: ["Shove the man away from your mother", '
            f'"Tell him your father is just around the corner", '
            f'"Slip behind the cart and hide"]\n'
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
        vignette_directive: str = "",
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
            state, action, nemesis_desc, eris_desc,
            epoch_phase=epoch_phase, vignette_directive=vignette_directive,
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
        vignette_directive: str = "",
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
            state, action, nemesis_desc, eris_desc,
            epoch_phase=epoch_phase, vignette_directive=vignette_directive,
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
