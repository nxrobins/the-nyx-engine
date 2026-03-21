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
    trust: float = 0.0
    fear: float = 0.0
    obligation: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class WorldSeed:
    settlement: str
    settlement_type: str
    region: str
    family: list[WorldNPC]
    social_class: str
    active_situation: str       # the plot engine for epoch 1
    world_facts: list[str]      # things that are true about this world
    home_location_id: str
    home_location_name: str
    home_location_kind: str
    home_condition: str
    faction_id: str
    faction_name: str
    faction_stance: str
    faction_notes: str
    relationship_hints: list[str] = field(default_factory=list)
    default_scene_problem: str = ""
    default_scene_objective: str = ""


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
            WorldNPC("Sera", "mother", "quiet", trust=1.5, obligation=1.0, tags=["family", "caretaker"]),
            WorldNPC("Aldric", "father", "absent", trust=0.5, obligation=0.5, tags=["family", "missing"]),
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
        home_location_id="thornwell_candlehouse",
        home_location_name="Sera's candlehouse",
        home_location_kind="family workshop",
        home_condition="Warm tallow smoke, rough tables, and shelves lined with cooling candles.",
        faction_id="thornwell_elders",
        faction_name="Elders of Thornwell",
        faction_stance="watchful",
        faction_notes="They ration trade news and decide what reaches the village.",
        relationship_hints=[
            "Sera protects the household by withholding what frightens the child.",
            "Aldric is absent but still shapes the household through debt and rumor.",
        ],
        default_scene_problem="The household is straining under Aldric's absence and the elder's silence.",
        default_scene_objective="Stay close, help Sera, and make sense of the unease in the house.",
    ),

    # "The weight of a heavy stone in my hand." → bia (force)
    "stone": WorldSeed(
        settlement="Ashfall",
        settlement_type="mining camp",
        region="the Northern Reaches",
        family=[
            WorldNPC("Maren", "mother", "exhausted", trust=1.0, obligation=1.0, tags=["family", "overworked"]),
            WorldNPC("Kael", "father", "hard", trust=0.6, fear=0.8, obligation=1.2, tags=["family", "miner"]),
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
        home_location_id="ashfall_hauler_shack",
        home_location_name="Hauler Row shack",
        home_location_kind="worker shack",
        home_condition="Coal dust clings to every blanket, and the floorboards creak under ore sacks.",
        faction_id="ashfall_mine_authority",
        faction_name="Ashfall Mine Authority",
        faction_stance="extractive",
        faction_notes="The mine boss Torval enforces quotas and punishes delay.",
        relationship_hints=[
            "Maren keeps the household running by sheer endurance.",
            "Kael's hardness is part fear of Torval and part fear of poverty.",
        ],
        default_scene_problem="The camp expects labor from everyone while the shaft collapse darkens every meal.",
        default_scene_objective="Avoid drawing Torval's attention while surviving the camp's demands.",
    ),

    # "A crowd shouting a name that was not mine." → kleos (glory/identity)
    "crowd": WorldSeed(
        settlement="Oldgate",
        settlement_type="walled market town",
        region="the Midvale",
        family=[
            WorldNPC("Halda", "mother", "proud", trust=1.0, obligation=0.8, tags=["family", "guarded"]),
            WorldNPC("Ren", "father", "boisterous", trust=0.8, fear=0.4, obligation=0.7, tags=["family", "hawker"]),
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
        home_location_id="oldgate_south_market",
        home_location_name="South Market blankets",
        home_location_kind="market pitch",
        home_condition="Boots churn mud around blankets of cheap goods and cooking smoke hangs low over the stalls.",
        faction_id="oldgate_voss_retinue",
        faction_name="Lord Voss's retinue",
        faction_stance="domineering",
        faction_notes="Armed soldiers distort the market whenever the retinue passes through.",
        relationship_hints=[
            "Halda fears disgrace more than hunger.",
            "Ren performs confidence because customers reward noise.",
        ],
        default_scene_problem="The market is overcrowded and the retinue can ruin a hawker family with a glance.",
        default_scene_objective="Stay close, stay useful, and survive the attention of soldiers and buyers.",
    ),

    # "A cold shadow that moved when I moved." → aidos (shadow/solitude)
    "shadow": WorldSeed(
        settlement="the Fenward",
        settlement_type="isolated farmstead",
        region="the Eastern Bogs",
        family=[
            WorldNPC("Gran", "grandmother", "silent", trust=1.0, fear=0.6, obligation=1.4, tags=["family", "keeper"]),
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
        home_location_id="fenward_stone_house",
        home_location_name="The Fenward stone house",
        home_location_kind="farmstead house",
        home_condition="Peat smoke leaks from the hearth while damp reeds dry beside the wall.",
        faction_id="crosshollow_neighbors",
        faction_name="Crosshollow neighbors",
        faction_stance="distant",
        faction_notes="Far enough away to be unreliable, close enough to matter in a crisis.",
        relationship_hints=[
            "Gran protects knowledge through silence.",
            "Isolation makes every small household problem feel enormous.",
        ],
        default_scene_problem="Isolation turns a sick goat and a silent elder into a genuine threat to survival.",
        default_scene_objective="Read Gran's mood, keep the household functioning, and decide whether to obey her limits.",
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
