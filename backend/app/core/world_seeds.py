"""World Seeds — deterministic world templates keyed by first memory.

Each memory archetype maps to a concrete starting world: a named
settlement, a family structure, a social class, key NPCs, and an
active situation that drives the first epoch's plot.

These are authorial, not generated. The game designer controls
the dramatic starting conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorldNPC:
    name: str
    role: str       # "mother", "father", "elder", "rival child"
    trait: str      # one-word behavioral tag: "stern", "gentle", "cruel"


@dataclass
class WorldSeed:
    settlement: str
    settlement_type: str
    region: str
    family: list[WorldNPC]
    social_class: str
    active_situation: str       # the plot engine for epoch 1
    world_facts: list[str]      # things that are true about this world


# ═══════════════════════════════════════════════════════════════
# Four world templates, one per first memory archetype
# ═══════════════════════════════════════════════════════════════

WORLD_SEEDS: dict[str, WorldSeed] = {
    # "A light in the distance I could not reach." → metis (curiosity)
    "light": WorldSeed(
        settlement="Thornwell",
        settlement_type="hill village",
        region="the Ashlands",
        family=[
            WorldNPC("Sera", "mother", "quiet"),
            WorldNPC("Aldric", "father", "absent"),
        ],
        social_class="chandler's family (candle-makers)",
        active_situation=(
            "Your father left for the southern trade road six months ago "
            "and has not returned. Your mother works the tallow alone. "
            "The village elder says the road is closed."
        ),
        world_facts=[
            "Thornwell sits on a ridge above a dead river",
            "The Ashlands got their name from the volcanic soil, not from fire",
            "The village has maybe forty families",
            "The elder is a woman named Bryd who walks with a stick",
            "There is a stone wall on the eastern side that nobody remembers building",
        ],
    ),

    # "The weight of a heavy stone in my hand." → bia (force)
    "stone": WorldSeed(
        settlement="Ashfall",
        settlement_type="mining camp",
        region="the Northern Reaches",
        family=[
            WorldNPC("Maren", "mother", "exhausted"),
            WorldNPC("Kael", "father", "hard"),
        ],
        social_class="ore-hauler family (lowest caste in the camp)",
        active_situation=(
            "The eastern shaft collapsed last week. Three men are still "
            "buried. Your father works double shifts. The mine boss says "
            "if the shaft isn't cleared by month's end, the camp moves."
        ),
        world_facts=[
            "Ashfall is not a village but a mining camp that follows the seam",
            "The ore is black iron, used for weapons",
            "Ore-haulers carry rock on their backs up the shaft ladders",
            "The mine boss is a man named Torval who answers to a lord nobody has seen",
            "Children work the sorting piles from age six",
        ],
    ),

    # "A crowd shouting a name that was not mine." → kleos (glory/identity)
    "crowd": WorldSeed(
        settlement="Oldgate",
        settlement_type="walled market town",
        region="the Midvale",
        family=[
            WorldNPC("Halda", "mother", "proud"),
            WorldNPC("Ren", "father", "boisterous"),
        ],
        social_class="market hawker family (loud, visible, not respected)",
        active_situation=(
            "A lord's retinue is passing through Oldgate. The market is "
            "packed. Your father is trying to sell to the soldiers. Your "
            "mother told you to stay close and not touch anything."
        ),
        world_facts=[
            "Oldgate is built around a gate in a wall that predates the town",
            "The market runs three days a week and is the town's only economy",
            "Market hawkers have no permanent stalls, just blankets on the ground",
            "The lord whose soldiers are here is Lord Voss, feared and rarely seen",
            "There is a well in the center of the market that children are told not to look into",
        ],
    ),

    # "A cold shadow that moved when I moved." → aidos (shadow/solitude)
    "shadow": WorldSeed(
        settlement="the Fenward",
        settlement_type="isolated farmstead",
        region="the Eastern Bogs",
        family=[
            WorldNPC("Gran", "grandmother", "silent"),
        ],
        social_class="bog-farmer (subsistence, no community)",
        active_situation=(
            "You live alone with your grandmother. She has not spoken in "
            "three days. The goat is sick. The nearest neighbor is a half-day's "
            "walk through the bog, and your grandmother forbids the path."
        ),
        world_facts=[
            "The Fenward is a single stone house on a rise above the bog",
            "Your parents are never mentioned and Gran will not answer questions about them",
            "The bog produces peat, rushes, and eels",
            "Something lives in the deeper bog that Gran calls 'the Mire'",
            "The nearest settlement is a village called Crosshollow",
        ],
    ),
}


def get_world_seed(first_memory: str) -> WorldSeed:
    """Match a first memory string to its world template.

    Falls back to 'shadow' if no keyword matches.
    """
    memory_lower = first_memory.lower()
    for keyword, seed in WORLD_SEEDS.items():
        if keyword in memory_lower:
            return seed
    return WORLD_SEEDS["shadow"]


def format_world_context(seed: WorldSeed, player_name: str, player_gender: str) -> str:
    """Format the world seed into a context block for Clotho and Lachesis.

    Returns a plain-text block that can be injected into prompts.
    """
    family_lines = []
    for npc in seed.family:
        family_lines.append(f"  - {npc.name} ({npc.role}, {npc.trait})")

    facts_lines = [f"  - {f}" for f in seed.world_facts]

    return (
        f"═══ THE WORLD ═══\n"
        f"Settlement: {seed.settlement} ({seed.settlement_type}, {seed.region})\n"
        f"Social class: {seed.social_class}\n"
        f"Family:\n" + "\n".join(family_lines) + "\n"
        f"Current situation: {seed.active_situation}\n"
        f"World facts:\n" + "\n".join(facts_lines)
    )
