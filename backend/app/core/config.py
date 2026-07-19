"""Engine configuration loaded from environment variables.

v2.0: LiteLLM model strings replace per-agent provider+model pairs.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # App
    app_name: str = "Nyx Engine"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM API keys
    anthropic_api_key: str = ""
    mercury_api_key: str = ""
    mercury_api_base: str = "https://api.inceptionlabs.ai/v1"

    # Agent model assignments (LiteLLM model strings)
    # Format: "provider/model" — LiteLLM routes automatically
    clotho_model: str = "anthropic/claude-sonnet-4-6"
    # THE PULSE: the cheap-beat prose surface. Vignette prose is digestible and
    # flow-first (Nigel's ruling) — haiku is the house tier for short literate
    # prose (Hypnos/Chronicler). Hard length bound lives at the call (P1-C9).
    clotho_vignette_model: str = "anthropic/claude-haiku-4-5-20251001"
    lachesis_model: str = "openai/mercury-2"
    nemesis_model: str = "openai/mercury-2"
    eris_model: str = "openai/mercury-2"
    hypnos_model: str = "anthropic/claude-haiku-4-5-20251001"
    chronicler_model: str = "anthropic/claude-haiku-4-5-20251001"
    morpheus_model: str = "anthropic/claude-sonnet-4-6"
    scribe_model: str = "anthropic/claude-sonnet-4-6"

    # The Throttle — reliability bounds on REAL-model calls (mock mode is
    # unaffected: each agent returns at its `model == "mock"` guard before any
    # acompletion). Small numbers so a brownout fails fast to the mock net
    # rather than stacking minutes across the sequential turn stage-chain.
    llm_request_timeout: float = 15.0   # per-call wall clock (THR-C4)
    llm_num_retries: int = 1            # litellm-internal retries; <=2 attempts/stage (THR-C4)
    llm_concurrency_budget: int = 32    # global in-flight real-model calls; > per-turn fan-out (THR-C5)
    llm_acquire_timeout: float = 30.0   # max wait for a budget slot before degrading to mock (THR-C5)
    session_count_cap: int = 256        # hard ceiling on live sessions; LRU-evict idle ones (THR-C6)

    # BFL (Black Forest Labs) — Image generation
    bfl_api_key: str = ""
    bfl_model: str = "flux.1-schnell"
    bfl_style_prefix: str = "Monochrome sumi-e ink wash"
    bfl_style_suffix: str = "black ink on aged parchment, no text, no UI elements"

    # World cartridges — empty = backend/worlds/ (module-relative, NC-3)
    worlds_dir: str = ""

    # Bound lives — empty = backend/books/ (module-relative, NC-3)
    books_dir: str = ""

    # Weighed lives — empty = backend/assays/ (module-relative, NC-3)
    assays_dir: str = ""

    # ChromaDB — empty = ephemeral in-memory
    chromadb_path: str = ""

    # PostgreSQL — empty = in-memory only (no persistence)
    database_url: str = ""
    sqlite_store_path: str = ""

    # Gameplay tuning
    nemesis_imbalance_threshold: float = 6.0
    eris_chaos_probability: float = 0.25
    soul_mirror_threshold: float = 7.0
    chronicle_interval: int = 5
    chronicle_prose_retention: int = 2
    hypnos_fragment_delay: float = 0.6
    # Relationship consequence: the betrayal_weight past which a witness departs
    # your life for good (status -> "departed"). 5.0 is the "no warmth returns"
    # point (canon._record_warming), so departure is its logical end — roughly
    # four deliberate betrayals of the same person.
    npc_depart_betrayal_weight: float = 5.0
    # The Witnesses Arrive: a latent NPC arrives only while the LIVING-present
    # cast is below this cap. Set to the family max_length so a dense world is
    # never dead-on-arrival for the feature (ARR-C11).
    arrival_present_cap: int = 12

    # Doom staging — death arrives in installments, not as a syntax error.
    # Escape thresholds are calibrated against pressure decay rates so an
    # escapable doom is survivable by play, not only by luck: wounds fall
    # 0.8/recovery turn (9.0 → 7.4 in two turns), faction heat falls
    # 0.4/lying-low turn (9.0 → 7.8 in three).
    wounds_doom_threshold: float = 9.0   # wounds pressure that starts bleeding out
    wounds_doom_escape: float = 7.5      # recovery below this lifts the doom
    faction_doom_threshold: float = 9.0  # faction heat that starts the manhunt
    faction_doom_escape: float = 8.0     # heat below this lifts the doom
    # Old age — a long, UNDOOMED thread bends toward a natural close. Below this
    # age no old-age doom begins; past it the decline loses ~one stage per decade.
    # A game-balance knob; the >= 18 lower bound is load-bearing (OLD-AG-1).
    old_age_threshold: int = 60

    @field_validator("old_age_threshold")
    @classmethod
    def _old_age_stays_adult(cls, v: int) -> int:
        # OLD-AG-1, ENFORCED (not just asserted in a test): the old-age doom
        # onset reads session.player_age directly (audit V2-C2 — it no longer
        # derives age from turn_count). Childhood player_age caps at 12, so a
        # threshold >= 18 can never fire in the childhood range; a sub-18 override
        # (OLD_AGE_THRESHOLD=10) could, re-enabling old-age death in childhood.
        # Fail closed, don't silently corrupt mortality.
        if v < 18:
            raise ValueError(
                f"old_age_threshold must be >= 18 (adult), got {v} — a sub-adult "
                f"threshold could fire old-age death in the childhood age range (OLD-AG-1)"
            )
        return v

    # Momus repair: hallucination count that justifies a full Clotho retry.
    # Below it, the deterministically corrected prose commits directly.
    momus_retry_min_issues: int = 2

    # Sophia — the semantic judge tier (Generative Adjudication). A second,
    # model-facing pass behind Momus's regex pre-filter, with ZERO state
    # authority. The issue-count -> action enforcement thresholds belong to
    # the Consequence Calibration axis, not here (ADJ-E6).
    sophia_model: str = "anthropic/claude-haiku-4-5-20251001"
    sophia_max_revisions: int = 1
    craft_notes_max: int = 3

    # Mock-mode latency simulation multiplier (tests set 0 to run instantly)
    mock_latency_scale: float = 1.0

    # Calibration harness (backend/sim/) — additive, read only by the
    # offline life-simulation harness, never by the game path (CAL-E8).
    sim_default_turn_cap: int = 40
    sim_baseline_path: str = ""   # empty = backend/sim/baseline.friction.json

    # CORS — origins allowed to call the API
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # The Vigil (Player Safety) — HARD merge gate. The full duty-of-care
    # SURFACE (consent UI, crisis-resource copy, ideation detection patterns,
    # the welfare classifier) is DEFERRED to human + clinical review and must
    # not render live until reviewed copy lands. See backend/SAFETY.md. Phase 1
    # ships only the pure-engineering floor: input redaction + death permanence.
    welfare_copy_reviewed: bool = False

    # Atropos death keywords — the FICTION self-destruction trigger. Matched
    # whole-phrase and negation-guarded (atropos.expresses_self_destruction).
    # Nigel's Vigil ruling (SAFE-C4 relaxed): the fiction death may be MORE
    # conservative than the real-human crisis detector. "jump off" is NOT here —
    # a bare leap is ambiguous ("jump off the cart"); the matcher's death-context
    # rule kills only "jump off a cliff / to my death". welfare.py keeps its broad
    # "jump off" so care still fires either way (crisis breadth is unchanged).
    atropos_death_keywords: list[str] = [
        "surrender to death",
        "embrace the void",
        "drink the poison",
        "end my thread",
        "cut my own thread",
        "give up completely",
        "welcome oblivion",
    ]

    # Hamartia options (immutable tragic flaws)
    hamartia_options: list[str] = [
        "Hubris of the Intellect",
        "Wrath of the Untempered",
        "Avarice Unbound",
        "Cowardice Veiled as Wisdom",
        "Pride That Blinds",
    ]


settings = Settings()
