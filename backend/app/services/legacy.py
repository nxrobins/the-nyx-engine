"""Legacy echoes — derive inherited marks from dead threads."""

from __future__ import annotations

from app.schemas.state import LegacyEcho


def _lower(value: object) -> str:
    return str(value or "").lower()


def build_legacy_echo(ancestor: dict | None) -> tuple[LegacyEcho | None, dict[str, float]]:
    """Create one narrative echo and one light mechanical modifier."""
    if not ancestor:
        return None, {}

    hamartia = str(ancestor.get("hamartia") or "")
    death_reason = _lower(ancestor.get("death_reason") or ancestor.get("epitaph"))
    thread_id = str(ancestor.get("thread_id") or ancestor.get("source_thread_id") or "")

    mark = "Ash Memory"
    effect_text = "Omen begins slightly higher."
    delta = {"omen": 0.35}

    if "oath" in death_reason:
        mark = "Oath-Scar"
        effect_text = "Suspicion begins slightly higher because the blood remembers a broken vow."
        delta = {"suspicion": 0.5}
    elif "wrath" in hamartia.lower():
        mark = "Battle Scar"
        effect_text = "Wounds begin slightly higher, as if violence lingers in the body."
        delta = {"wounds": 0.4}
    elif any(word in hamartia.lower() for word in ("hubris", "pride", "vainglory", "avarice")):
        mark = "Crowd's Memory"
        effect_text = "Suspicion and faction heat begin slightly higher; people notice this bloodline."
        delta = {"suspicion": 0.3, "faction_heat": 0.25}
    elif "coward" in hamartia.lower():
        mark = "Whisper of Shame"
        effect_text = "Faction heat begins slightly higher; retreat has left a social stain."
        delta = {"faction_heat": 0.4}

    echo = LegacyEcho(
        source_thread_id=thread_id,
        epitaph=str(ancestor.get("epitaph") or "A thread lost to silence."),
        hamartia=hamartia,
        inherited_mark=mark,
        mechanical_effect=effect_text,
    )
    return echo, delta


def augment_thread_summary(thread: dict) -> dict:
    """Attach legacy-facing summary fields for the title screen."""
    echo, _ = build_legacy_echo(thread)
    summary = dict(thread)
    if echo is not None:
        summary["legacy_mark"] = echo.inherited_mark
        summary["legacy_effect"] = echo.mechanical_effect
    else:
        summary["legacy_mark"] = ""
        summary["legacy_effect"] = ""
    return summary
