"""Prompt Loader — reads agent system prompts from YAML files.

Loads once per process, caches in a module-level dict. Thread-safe for
read-after-init (no mutations after startup).

Usage:
    from app.services.prompt_loader import load_prompt
    CLOTHO_SYSTEM_PROMPT = load_prompt("clotho")
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger("nyx.prompt_loader")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_cache: dict[str, str] = {}


def load_prompt(agent_name: str) -> str:
    """Load a system prompt by agent name (e.g. 'clotho', 'lachesis').

    Returns the cached prompt string. Raises FileNotFoundError if the
    YAML file doesn't exist, ValueError if the YAML is malformed.
    """
    if agent_name in _cache:
        return _cache[agent_name]

    yaml_path = _PROMPTS_DIR / f"{agent_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {yaml_path}. "
            f"Expected YAML at app/prompts/{agent_name}.yaml"
        )

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "system_prompt" not in data:
        raise ValueError(
            f"Malformed prompt file: {yaml_path}. "
            f"Expected a YAML dict with a 'system_prompt' key."
        )

    prompt = data["system_prompt"].strip()
    _cache[agent_name] = prompt
    logger.debug("Loaded prompt for %s (%d chars)", agent_name, len(prompt))
    return prompt


def reload_prompt(agent_name: str) -> str:
    """Force-reload a prompt from disk (useful for hot-reload in dev)."""
    _cache.pop(agent_name, None)
    return load_prompt(agent_name)


def reload_all() -> None:
    """Clear the cache and reload all prompts from disk."""
    _cache.clear()
    for yaml_file in _PROMPTS_DIR.glob("*.yaml"):
        agent_name = yaml_file.stem
        load_prompt(agent_name)
    logger.info("Reloaded %d prompts from %s", len(_cache), _PROMPTS_DIR)
