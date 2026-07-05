"""Hand-authored vignette pools for the four builtin worlds (Phase 1, sub-slice 2).

These are AUTHORED, not generated — the world-seeds trick again: a small,
hand-written deck per builtin proves the vignette contract before THE FACTORY
(Phase 3) industrializes authorship. Every situation is grounded in its world's
canon facts (Thornwell's dead river and unremembered wall; Ashfall's black iron
and rotting ladders; Oldgate's market, well, and Lord Voss; the Fenward's bog
and the Mire). Each choice is a concrete physical act; the packet is the whole
consequence — the deterministic layer applies it with no council.

Validated by the schema at import (caps, movement floor, vector span) and by
tests that walk every pool.
"""

from __future__ import annotations

from app.schemas.vignette import (
    ConsequencePacket,
    Vignette,
    VignetteChoice,
    VignettePool,
)


def _c(label: str, *, vec: dict[str, float] | None = None,
       press: dict[str, float] | None = None, bond: float = 0.0,
       evo: str = "") -> VignetteChoice:
    return VignetteChoice(
        label=label,
        packet=ConsequencePacket(
            vector_deltas=vec or {}, pressure_deltas=press or {},
            bond_delta=bond, scene_evolution=evo,
        ),
    )


# ── THORNWELL (builtin-light) — hill village above a dead river ──────────────

_THORNWELL = VignettePool(world_id="builtin-light", vignettes=[
    Vignette(
        vignette_id="thornwell_tallow_short",
        situation=(
            "The autumn render comes up short — two barrels where there should be five, "
            "and the winter candle orders already promised. {mother} recounts the barrels "
            "as if counting could change them."
        ),
        cast_slots=["mother"],
        choices=[
            _c("Lean on the tallow supplier for what he owes",
               vec={"bia": 0.7}, press={"faction_heat": 0.3},
               evo="The supplier pays up — and starts telling people you squeeze."),
            _c("Stretch the render with lard and say nothing",
               vec={"metis": 0.7}, press={"suspicion": 0.4},
               evo="The candles burn greasy. Someone will notice by midwinter."),
            _c("Cut the family's own candles first and sell the rest honest",
               vec={"aidos": 0.7}, press={"scarcity": 0.4}, bond=0.5,
               evo="Dark evenings at home; a reputation for fair weight abroad."),
        ],
    ),
    Vignette(
        vignette_id="thornwell_wall_stone",
        situation=(
            "A stone has fallen from the eastern wall — the wall nobody remembers "
            "building. It lies in the grass like a pulled tooth. Old folk spit when "
            "they pass it; children dare each other to touch."
        ),
        choices=[
            _c("Set the stone back with your own hands, in daylight",
               vec={"kleos": 0.6}, press={"omen": -0.2},
               evo="The village watched you do it. The wall looks whole; you look bold."),
            _c("Study the socket it fell from before anyone interferes",
               vec={"metis": 0.6}, press={"omen": 0.2},
               evo="There is older stone behind the stone. The wall has an inside."),
            _c("Leave it where it lies and keep walking",
               vec={"aidos": 0.5},
               evo="The stone stays in the grass. The dares get worse."),
        ],
    ),
    Vignette(
        vignette_id="thornwell_road_rumor",
        situation=(
            "A peddler in the square swears the southern trade road is open again — "
            "and, for a coin, sells news of those it swallowed years ago. His eyes "
            "find yours over the crowd, and he smiles like a man who knows a name."
        ),
        choices=[
            _c("Pay him and hear the name out",
               vec={"metis": 0.5}, press={"scarcity": 0.2, "omen": 0.3},
               evo="What he sold you doesn't fit what you remember. One of them is lying."),
            _c("Call him a grave-robber in front of his customers",
               vec={"bia": 0.7}, press={"faction_heat": 0.3},
               evo="The crowd turns. The peddler packs — slowly, memorizing your face."),
            _c("Walk away with your coin and your dead",
               vec={"aidos": 0.6},
               evo="The peddler sells the name to someone else. You watch them pay."),
        ],
    ),
    Vignette(
        vignette_id="thornwell_bryd_ledger",
        situation=(
            "Elder Bryd walks slower now, but her stick still finds every loose plank in "
            "Thornwell. She keeps the ledger of who owes what to whom — and she has "
            "let it be known she wants someone to learn it. People watch her door."
        ),
        choices=[
            _c("Knock on her door before anyone else does",
               vec={"kleos": 0.7}, press={"suspicion": 0.3},
               evo="She sets the ledger before you, open to a page with your family's name."),
            _c("Learn who else wants the ledger, and what they'd do with it",
               vec={"metis": 0.7},
               evo="Three names. Two owe money. The third owes something worse."),
            _c("Stay clear — debts written down are debts remembered",
               vec={"aidos": 0.6},
               evo="The door opens for someone else. Bryd's eyes find you anyway."),
        ],
    ),
    Vignette(
        vignette_id="thornwell_black_water",
        situation=(
            "For one night the dead river ran — black water, quick and quiet, gone by "
            "dawn. You saw it from the ridge. So did one other person, and by noon the "
            "village is already deciding it never happened."
        ),
        choices=[
            _c("Stand in the square and say what you saw",
               vec={"kleos": 0.8}, press={"suspicion": 0.4, "omen": 0.3},
               evo="Half the village thinks you're touched. The other half starts watching the riverbed."),
            _c("Compare accounts with the other witness, privately",
               vec={"metis": 0.6}, press={"omen": 0.2},
               evo="Their account matches yours — except for what stood on the far bank."),
            _c("Let the village have its comfortable forgetting",
               vec={"aidos": 0.6}, press={"omen": 0.2},
               evo="The riverbed stays dry. Your boots, from that night, stay stained."),
        ],
    ),
])


# ── ASHFALL (builtin-stone) — mining camp on the black iron seam ─────────────

_ASHFALL = VignettePool(world_id="builtin-stone", vignettes=[
    Vignette(
        vignette_id="ashfall_short_weigh",
        situation=(
            "The weigh-master's scale reads light for your crew three days running — "
            "same rock, same carts, less credit. Wages follow the scale, and the "
            "scale follows someone's thumb."
        ),
        choices=[
            _c("Drop your ore at his feet and demand a true weigh",
               vec={"bia": 0.8}, press={"faction_heat": 0.4},
               evo="He reweighs under your stare. The camp hears the number — and his excuse."),
            _c("Mark your carts secretly and build the proof first",
               vec={"metis": 0.8}, press={"suspicion": 0.2},
               evo="Four marked carts, four light weighs, one ledger that can hang him."),
            _c("Take the light credit and keep your head down",
               vec={"aidos": 0.6}, press={"scarcity": 0.3},
               evo="The thumb gets bolder. Your crew starts looking at you differently."),
        ],
    ),
    Vignette(
        vignette_id="ashfall_ladder_rot",
        situation=(
            "The shaft ladders are going soft — you felt a rung give under your boot "
            "this morning, forty feet above the sump. Fixing them is nobody's paid "
            "work. Not fixing them is somebody's funeral, eventually."
        ),
        choices=[
            _c("Fix the worst rungs yourself, on your own time",
               vec={"aidos": 0.8}, press={"scarcity": 0.2},
               evo="Nobody thanks you. Nobody falls, either. The wood was worse than you thought."),
            _c("Rally the crews to refuse the shaft until it's timbered",
               vec={"kleos": 0.8}, press={"faction_heat": 0.6},
               evo="The shaft stands empty a full shift. The camp boss starts asking who started it."),
            _c("Corner the boss with the broken rung in your hand",
               vec={"bia": 0.7}, press={"faction_heat": 0.3},
               evo="He budgets timber for one ladder. One. You choose which shaft lives."),
        ],
    ),
    Vignette(
        vignette_id="ashfall_company_scrip",
        situation=(
            "Pay comes in company scrip now — little tin promises good only at the camp "
            "store, where the prices climbed the same week. Real coin leaves camp in a "
            "locked box under guard."
        ),
        choices=[
            _c("Run quiet trades with the drovers for real coin",
               vec={"metis": 0.8}, press={"suspicion": 0.5},
               evo="You get silver at a cruel rate. The store clerk starts counting your visits."),
            _c("Organize the crews to demand coin wages back",
               vec={"kleos": 0.7}, press={"faction_heat": 0.6},
               evo="Forty names on a paper. The paper goes up the hill to a lord nobody has seen."),
            _c("Live on scrip and stockpile what keeps",
               vec={"aidos": 0.6}, press={"scarcity": 0.4},
               evo="Your shelf fills with salt and nails. Your neighbors' shelves don't."),
        ],
    ),
    Vignette(
        vignette_id="ashfall_wrong_seam",
        situation=(
            "The new seam glitters wrong — too bright in the lamplight, and the old "
            "miners spit and won't name it. Quota says dig. The rock says otherwise, "
            "in a language your hands are starting to understand."
        ),
        choices=[
            _c("Dig it anyway and make quota",
               vec={"bia": 0.6}, press={"omen": 0.4, "wounds": 0.2},
               evo="The ore comes out humming-cold. The assayer pays double and asks no questions."),
            _c("Bring a lamp and a sample to the oldest miner, after shift",
               vec={"metis": 0.7}, press={"omen": 0.2},
               evo="He looks once, closes your hand over the sample, and tells you to bury it."),
            _c("Work a different face and let another crew take the glitter",
               vec={"aidos": 0.6},
               evo="The other crew makes quota twice over. Their cough starts a week later."),
        ],
    ),
    Vignette(
        vignette_id="ashfall_buried_bell",
        situation=(
            "From the gallery everyone calls settled — sealed since the collapse — "
            "comes a sound on the night shift. Tap. Tap-tap. Tap. Old code, the kind "
            "haulers used before your time. The seal has held for years."
        ),
        choices=[
            _c("Break the seal and dig toward the sound",
               vec={"bia": 0.8}, press={"wounds": 0.3, "omen": 0.3},
               evo="Behind the seal: fresh air where there should be none, and the tapping — closer."),
            _c("Raise the whole night shift to witness it first",
               vec={"kleos": 0.7}, press={"faction_heat": 0.3, "omen": 0.3},
               evo="Twelve haulers hear it answer a question. The boss orders the gallery re-sealed."),
            _c("Mark the rhythm, tell no one, and listen again tomorrow",
               vec={"metis": 0.7}, press={"omen": 0.4},
               evo="The rhythm repeats exactly. It is not a survivor. Survivors improvise."),
        ],
    ),
])


# ── OLDGATE (builtin-crowd) — walled market town under Lord Voss ─────────────

_OLDGATE = VignettePool(world_id="builtin-crowd", vignettes=[
    Vignette(
        vignette_id="oldgate_stall_rights",
        situation=(
            "A permanent stall by the old gate falls vacant — canvas, timber, and a "
            "spot the morning sun crosses first. The market master accepts "
            "'considerations.' Every hawker with a blanket knows it by noon."
        ),
        choices=[
            _c("Outbid them all, loudly, in the open square",
               vec={"kleos": 0.8}, press={"debt": 0.5},
               evo="The stall is yours and half the market owes you envy. The loan, you owe elsewhere."),
            _c("Find what the market master actually wants — it isn't coin",
               vec={"metis": 0.8}, press={"suspicion": 0.3},
               evo="It's a name he wants. You know the name. Knowing it is now a debt too."),
            _c("Keep your blanket pitch and your independence",
               vec={"aidos": 0.6},
               evo="The stall goes to a spice seller. Your corner of ground feels smaller."),
        ],
    ),
    Vignette(
        vignette_id="oldgate_voss_levy",
        situation=(
            "New parchment on the gate: Lord Voss levies a 'wall tax' on every blanket "
            "and stall, effective the next market day. The soldiers posting it don't "
            "meet anyone's eyes. The hawkers' row goes quiet, then loud."
        ),
        choices=[
            _c("Put your name first on a petition against the levy",
               vec={"kleos": 0.8}, press={"faction_heat": 0.6},
               evo="Eleven names follow yours. A clerk copies all twelve for the keep."),
            _c("Restructure your pitch to fall between the levy's words",
               vec={"metis": 0.8}, press={"suspicion": 0.3},
               evo="You sell 'from a basket, walking' now. The collector squints at his own parchment."),
            _c("Pay it and pass the cost quietly into your prices",
               vec={"aidos": 0.5}, press={"scarcity": 0.3},
               evo="Your bread costs a copper more. Nobody starves; nobody forgets either."),
        ],
    ),
    Vignette(
        vignette_id="oldgate_well_coin",
        situation=(
            "A stranger in travel-grey offers you real silver to drop a small sealed "
            "box down the market well at midnight — the well children are told not to "
            "look into. He counts out half in advance without being asked."
        ),
        choices=[
            _c("Break the seal first and look inside",
               vec={"metis": 0.8}, press={"omen": 0.5, "suspicion": 0.2},
               evo="Inside: a lock of hair, a milk tooth, and a name written eleven times."),
            _c("Refuse and walk him to the watch, coin and all",
               vec={"kleos": 0.6}, press={"faction_heat": 0.3},
               evo="The watch takes your report and lets him go by morning. The silver is gone. He isn't."),
            _c("Do exactly what was paid for, at exactly midnight",
               vec={"aidos": 0.5}, press={"omen": 0.6, "debt": -0.3},
               evo="The box never splashes. The stranger pays the balance and doesn't count it."),
        ],
    ),
    Vignette(
        vignette_id="oldgate_family_pitch",
        situation=(
            "The pitch by the gate — the one your family held with blankets and lungs "
            "since before you could walk — has been taken at dawn by a younger crew "
            "with matching aprons and a paid receipt. {father} stands at the edge of it, "
            "holding a rolled blanket like a question."
        ),
        cast_slots=["father"],
        choices=[
            _c("Plant the family blanket in the middle of their receipt",
               vec={"bia": 0.8}, press={"faction_heat": 0.4}, bond=0.6,
               evo="The aprons blink first. The crowd remembers whose corner this was — today."),
            _c("Read their receipt closely enough to find its flaw",
               vec={"metis": 0.7}, bond=0.3,
               evo="The receipt names the wrong gate. Filed at the keep, that's worth exactly one dawn."),
            _c("Set up across the row and let the customers choose",
               vec={"aidos": 0.6}, press={"scarcity": 0.2}, bond=0.2,
               evo="Half the old customers cross the row. Half don't. Everyone counts."),
        ],
    ),
    Vignette(
        vignette_id="oldgate_lead_coin",
        situation=(
            "The fat coin you took this morning is lead under a silver skin — you feel "
            "it now, too late, warm in your palm. You know exactly which smiling "
            "regular passed it, and he's three stalls down doing it again."
        ),
        choices=[
            _c("Take his wrist over the next stall's table",
               vec={"bia": 0.7}, press={"faction_heat": 0.3},
               evo="Coins scatter — three more lead ones among them, in front of witnesses."),
            _c("Pass it onward in your own change, to someone who deserves it",
               vec={"metis": 0.6}, press={"suspicion": 0.5},
               evo="The coin moves on. So does the habit, a little easier the second time."),
            _c("Eat the loss and quietly warn the row",
               vec={"aidos": 0.7},
               evo="By noon every hawker weighs his silver. The smiling man stops smiling."),
        ],
    ),
])


# ── THE FENWARD (builtin-shadow) — a lone farmstead above the bog ────────────

_FENWARD = VignettePool(world_id="builtin-shadow", vignettes=[
    Vignette(
        vignette_id="fenward_eel_run",
        situation=(
            "The eel run comes early this year — the bog's one true harvest, and it "
            "waits for no one. The best nets must be set at dusk in the deep channels, "
            "past where the path is spoken for."
        ),
        choices=[
            _c("Set the nets in the deep channels yourself, at dusk",
               vec={"bia": 0.7}, press={"wounds": 0.2, "omen": 0.2},
               evo="The nets come up heavy. Something took a share first, and left the heads."),
            _c("Rig guide-ropes and lantern-marks before going in",
               vec={"metis": 0.7}, press={"scarcity": -0.2},
               evo="Slower, safer, fuller. The rope line stays behind — a path where none was."),
            _c("Work only the near shallows and accept the smaller catch",
               vec={"aidos": 0.6}, press={"scarcity": 0.3},
               evo="Half a harvest, whole boots. The deep channels churn at dusk without you."),
        ],
    ),
    Vignette(
        vignette_id="fenward_crosshollow_trader",
        situation=(
            "A trader out of Crosshollow stands at the edge of the rise, careful not to "
            "step past it. He wants winter peat at half its worth — and mentions, "
            "twice, how much friendlier the path stays for farms that trade with him."
        ),
        choices=[
            _c("Name your true price and hold it to his face",
               vec={"bia": 0.7}, press={"faction_heat": 0.3},
               evo="He pays full, smiling badly. The path home takes him twice as long as it should."),
            _c("Agree — then shade every measure in your favor",
               vec={"metis": 0.7}, press={"suspicion": 0.4},
               evo="Light stacks, damp cores. He won't know until the first cold week. You will."),
            _c("Sell at his price and buy the quiet",
               vec={"aidos": 0.5}, press={"scarcity": 0.4},
               evo="The peat goes cheap. The path stays 'friendly.' Both facts have a price next year."),
        ],
    ),
    Vignette(
        vignette_id="fenward_peat_box",
        situation=(
            "The cutting spade rings on iron: a small box, bog-black, surfacing from "
            "peat that hasn't been turned in a lifetime. The lock is rust. A name was "
            "scratched into the lid once — and scratched OUT harder."
        ),
        choices=[
            _c("Break the rust and open it where you stand",
               vec={"bia": 0.6}, press={"omen": 0.5},
               evo="Inside: a christening spoon, bent double, and a folded paper the damp got to. Almost."),
            _c("Take a rubbing of the scratched lid before touching the lock",
               vec={"metis": 0.7}, press={"omen": 0.3},
               evo="Under charcoal, the murdered name half-returns. It is one letter off your own."),
            _c("Put it back deeper than you found it",
               vec={"aidos": 0.7}, press={"omen": 0.4},
               evo="The peat takes it without a sound. The cutting is done for the day. Or the year."),
        ],
    ),
    Vignette(
        vignette_id="fenward_mire_light",
        situation=(
            "Two nights running, a light stands over the Mire — steady, patient, the "
            "height a lantern would be if anything out there had a hand to hold one. "
            "Crosshollow pays copper for Mire-stories. It pays silver for proof."
        ),
        choices=[
            _c("Carry the tale to Crosshollow and tell it well",
               vec={"kleos": 0.8}, press={"scarcity": -0.3, "omen": 0.3},
               evo="They pay copper, then buy you ale to tell it twice. Someone in the back doesn't laugh."),
            _c("Watch it from the rise with a sight-line and a count",
               vec={"metis": 0.7}, press={"omen": 0.4},
               evo="It does not wander. It BREATHES — brighter, dimmer, twelve counts each. Like sleep."),
            _c("Shutter the windows and salt the doorstone",
               vec={"aidos": 0.6}, press={"omen": 0.2},
               evo="The third night, the light is gone. The salt line, by morning, is crossed — outward."),
        ],
    ),
    Vignette(
        vignette_id="fenward_bog_body",
        situation=(
            "The bog gives one back: leather-brown, whole as sleep, a bronze knife "
            "still laced to its belt — older than Crosshollow, older maybe than the "
            "path. The bog keeps what it's given. Everyone out here knows that."
        ),
        choices=[
            _c("Take the bronze knife before the peat closes over",
               vec={"bia": 0.6}, press={"omen": 0.6},
               evo="The blade cleans up sharp and cold. Nights after, the cutting-field looks disturbed."),
            _c("Study the body where it lies — the clothes, the knots, the wound",
               vec={"metis": 0.8}, press={"omen": 0.3},
               evo="No wound at all. The knots are on the wrong side. They were tied by someone else."),
            _c("Give it back to the bog with the words Gran would have used",
               vec={"aidos": 0.8}, press={"omen": -0.3},
               evo="The peat closes like water. The bog is quiet after — quieter than it's been all year."),
        ],
    ),
])


_POOLS: dict[str, VignettePool] = {
    pool.world_id: pool for pool in (_THORNWELL, _ASHFALL, _OLDGATE, _FENWARD)
}


def pool_for_world(world_id: str) -> VignettePool | None:
    """The authored deck for a world, or None (dry pool — caller falls back loudly)."""
    return _POOLS.get(world_id)
