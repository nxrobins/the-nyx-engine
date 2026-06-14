"""The authored corpus — scripted lives + paraphrase pairs.

Every script is a fixed action list with a pinned seed; a seed/action edit
is a deliberate baseline regeneration. Ground-truth exploit labels and the
paraphrase pairs are hand-authored from in-fiction intent, NEVER from the
engine's predicates (CAL-E4), so the metrics can register the leaks the
engine misses.

Archetype → frozen world: light→thornwell, stone→ashfall, crowd→oldgate,
shadow→fenward.
"""

from __future__ import annotations

from sim.life_script import LifeScript, ParaphrasePair

_LIGHT = "A light in the distance I could not reach."
_STONE = "The weight of a heavy stone in my hand."
_CROWD = "A crowd shouting a name that was not mine."
_SHADOW = "A cold shadow that moved when I moved."

# Varied, non-abusive, non-repeating actions — committed-but-legitimate play
# that the consequence layer MUST leave unpunished (CAL-E7).
_LEGIT_ACTIONS = (
    "help the farmer bring in the harvest",
    "share bread with the beggar at the gate",
    "mend the old fence behind the cottage",
    "fetch water from the well for my mother",
    "greet the village elder by the chapel",
    "tend to the goats on the green hill",
    "listen to the harper's quiet song",
    "walk the long road toward the market",
)

_VARIED_ATTACKS = tuple(
    f"attack the {foe}" for foe in (
        "guard", "soldier", "beast", "rival", "thug", "captain", "raider",
        "wolf", "bandit", "brute", "knight", "ogre", "giant", "champion",
        "warden", "reaver", "marauder", "sentinel", "outrider", "berserker",
    )
)


SCRIPTS: list[LifeScript] = [
    # --- broken_oath (inescapable doom; also the inescapable doom-escape
    #     red-team: rest after the break, yet it still matures) ---
    LifeScript(
        label="oath_break_stone",
        first_memory=_STONE, hamartia="Wrath of the Untempered",
        actions=("I swear to protect my brother Edric.", "attack my brother Edric",
                 "rest", "rest", "rest"),
        expected_world_id="ashfall", expected_death_bucket="broken_oath", seed=101,
    ),
    LifeScript(
        label="oath_break_crowd",
        first_memory=_CROWD, hamartia="Pride That Blinds",
        actions=("I vow to protect the elder Mara.", "rest",
                 "strike the elder Mara", "hide", "rest", "rest"),
        expected_world_id="oldgate", expected_death_bucket="broken_oath", seed=102,
    ),

    # --- self_destruction keyword (immediate; Eris off, so no miracle) ---
    LifeScript(
        label="void_light",
        first_memory=_LIGHT, hamartia="Hubris of the Intellect",
        actions=("embrace the void",),
        expected_world_id="thornwell", expected_death_bucket="self_destruct_keyword", seed=103,
    ),
    LifeScript(
        label="surrender_shadow",
        first_memory=_SHADOW, hamartia="Cowardice Veiled as Wisdom",
        actions=("observe the dark", "i give up completely"),
        expected_world_id="fenward", expected_death_bucket="self_destruct_keyword", seed=104,
    ),

    # --- wounds doom (escapable in name; the fail path reliably matures) ---
    LifeScript(
        label="wounds_fail_stone",
        first_memory=_STONE, hamartia="Wrath of the Untempered",
        actions=_VARIED_ATTACKS,
        expected_world_id="ashfall", expected_death_bucket="wounds", seed=105,
    ),
    # --- wounds doom escape ATTEMPT (rest once the doom lands) — exploratory;
    #     the harness reports whether the staged window is actually escapable ---
    LifeScript(
        label="wounds_escape_try_stone",
        first_memory=_STONE, hamartia="Wrath of the Untempered",
        actions=_VARIED_ATTACKS[:13] + ("rest", "rest", "rest", "rest", "rest"),
        expected_world_id="ashfall", seed=106,
    ),

    # --- exploit-spam: identical repeated theft → exploit → punishment.
    #     Ground-truth: every turn is an exploit. The engine lags (the first
    #     turns before exploit>=2 are missed) → recall < 1 in part here. ---
    LifeScript(
        label="exploit_spam_shadow",
        first_memory=_SHADOW, hamartia="Avarice Unbound",
        actions=tuple(["steal the merchant's purse"] * 12),
        is_exploit_turn=tuple([True] * 12),
        expected_world_id="fenward", expected_death_bucket="__capped__", seed=107,
    ),

    # --- the SEMANTIC-REPEAT leak: paraphrased thefts that miss the exact
    #     repeat term AND mostly miss the keyword vocabulary. Ground-truth is
    #     exploit on every turn; the engine registers almost none →
    #     exploit_recall < 1.0 BY CONSTRUCTION (CAL-E4/E7 non-tautology). ---
    LifeScript(
        label="semantic_repeat_light",
        first_memory=_LIGHT, hamartia="Avarice Unbound",
        actions=("pilfer a loaf from the stall", "filch an apple from the cart",
                 "palm a coin from the tray", "lift a ring from the table",
                 "pocket a brooch from the bench", "spirit away a candlestick"),
        is_exploit_turn=tuple([True] * 6),
        expected_world_id="thornwell", expected_death_bucket="__capped__", seed=108,
    ),

    # --- long-quiet survivors → __capped__ (also the locked compliance-floor
    #     corpus: committed-but-legitimate play that MUST stay unpunished) ---
    LifeScript(
        label="legit_crowd",
        first_memory=_CROWD, hamartia="Pride That Blinds",
        actions=_LEGIT_ACTIONS, is_exploit_turn=tuple([False] * len(_LEGIT_ACTIONS)),
        expected_world_id="oldgate", expected_death_bucket="__capped__",
        legitimate=True, seed=109,
    ),
    LifeScript(
        label="legit_light",
        first_memory=_LIGHT, hamartia="Cowardice Veiled as Wisdom",
        actions=_LEGIT_ACTIONS, is_exploit_turn=tuple([False] * len(_LEGIT_ACTIONS)),
        expected_world_id="thornwell", expected_death_bucket="__capped__",
        legitimate=True, seed=110,
    ),
    LifeScript(
        label="legit_shadow",
        first_memory=_SHADOW, hamartia="Hubris of the Intellect",
        actions=_LEGIT_ACTIONS, is_exploit_turn=tuple([False] * len(_LEGIT_ACTIONS)),
        expected_world_id="fenward", expected_death_bucket="__capped__",
        legitimate=True, seed=111,
    ),
]


# The keyword-evasion attack surface: plain hits the vocabulary, smuggled
# carries identical in-fiction intent but misses every token.
PARAPHRASE_PAIRS: list[ParaphrasePair] = [
    ParaphrasePair("violence_guard", "attack the guard",
                   "introduce the guard's skull to the cobblestones",
                   "violent", "wounds+suspicion+faction_heat"),
    ParaphrasePair("violence_merchant", "stab the merchant",
                   "open the merchant from collar to hip",
                   "violent", "wounds+suspicion+faction_heat"),
    ParaphrasePair("deception_ledger", "steal the ledger",
                   "quietly relocate the ledger to my satchel",
                   "deceptive", "suspicion+exploit_score"),
    ParaphrasePair("deception_magistrate", "lie to the magistrate",
                   "offer the magistrate a more convenient truth",
                   "deceptive", "suspicion+exploit_score"),
    ParaphrasePair("deception_lock", "pickpocket the steward",
                   "let the steward's coin find a new pocket",
                   "deceptive", "suspicion+exploit_score"),
    ParaphrasePair("public_boast", "boast of my conquest in the square",
                   "let the tale of my conquest spread on its own",
                   "public", "suspicion+faction_heat"),
    ParaphrasePair("public_challenge", "challenge the captain before the crowd",
                   "make it impossible for the captain to refuse me before the crowd",
                   "public", "suspicion+faction_heat"),
    ParaphrasePair("resource_grain", "steal the grain stores",
                   "redistribute the grain stores in my favor",
                   "deceptive", "suspicion+exploit_score"),
]
