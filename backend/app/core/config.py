"""Engine configuration loaded from environment variables.

v2.0: LiteLLM model strings replace per-agent provider+model pairs.
"""

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
    clotho_model: str = "anthropic/claude-sonnet-4-20250514"
    lachesis_model: str = "openai/mercury-2"
    nemesis_model: str = "openai/mercury-2"
    eris_model: str = "openai/mercury-2"
    hypnos_model: str = "anthropic/claude-haiku-4-5-20251001"
    chronicler_model: str = "anthropic/claude-haiku-4-5-20251001"

    # BFL (Black Forest Labs) — Image generation
    bfl_api_key: str = ""
    bfl_model: str = "flux.1-schnell"
    bfl_style_prefix: str = "Monochrome sumi-e ink wash"
    bfl_style_suffix: str = "black ink on aged parchment, no text, no UI elements"

    # World cartridges — empty = backend/worlds/ (module-relative, NC-3)
    worlds_dir: str = ""

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

    # Doom staging — death arrives in installments, not as a syntax error.
    # Escape thresholds are calibrated against pressure decay rates so an
    # escapable doom is survivable by play, not only by luck: wounds fall
    # 0.8/recovery turn (9.0 → 7.4 in two turns), faction heat falls
    # 0.4/lying-low turn (9.0 → 7.8 in three).
    wounds_doom_threshold: float = 9.0   # wounds pressure that starts bleeding out
    wounds_doom_escape: float = 7.5      # recovery below this lifts the doom
    faction_doom_threshold: float = 9.0  # faction heat that starts the manhunt
    faction_doom_escape: float = 8.0     # heat below this lifts the doom

    # Momus repair: hallucination count that justifies a full Clotho retry.
    # Below it, the deterministically corrected prose commits directly.
    momus_retry_min_issues: int = 2

    # Mock-mode latency simulation multiplier (tests set 0 to run instantly)
    mock_latency_scale: float = 1.0

    # CORS — origins allowed to call the API
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Atropos death keywords (self-destruction triggers)
    atropos_death_keywords: list[str] = [
        "surrender to death",
        "embrace the void",
        "drink the poison",
        "jump off",
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
