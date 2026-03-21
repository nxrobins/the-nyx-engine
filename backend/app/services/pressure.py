"""Pressure Engine — persistent external consequence and instability rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.schemas.state import PressureState, ThreadState

if TYPE_CHECKING:
    from app.core.resolver import ResolvedOutcome

_VIOLENT_WORDS = {
    "attack", "strike", "stab", "kill", "cut", "smash", "break", "fight",
    "beat", "shove", "threaten", "burn", "maim",
}
_DECEPTIVE_WORDS = {
    "lie", "trick", "steal", "cheat", "deceive", "sneak", "hide", "forge",
    "con", "swindle", "pickpocket",
}
_PUBLIC_WORDS = {
    "shout", "declare", "challenge", "boast", "announce", "demand", "accuse",
    "sing", "proclaim",
}
_RECOVERY_WORDS = {
    "rest", "sleep", "bandage", "bind", "heal", "wash", "breathe", "hide",
    "treat",
}
_RESOURCE_WORDS = {"buy", "beg", "borrow", "take", "steal", "gather", "forage"}
_PAYMENT_WORDS = {"pay", "repay", "settle", "return", "work", "trade"}
_CAUTIOUS_WORDS = {"wait", "hide", "watch", "observe", "retreat", "flee"}


@dataclass(slots=True)
class PressureEvolution:
    """Result of one turn of pressure evolution."""
    delta: dict[str, float]
    stable_turn: bool
    summary: str


def _normalize_action(action: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", action.lower()).strip()


def _contains_any(action: str, words: set[str]) -> bool:
    tokens = set(_normalize_action(action).split())
    return bool(tokens & words)


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, value))


def pressure_summary(state: ThreadState | PressureState) -> str:
    """Render the most salient active pressures for prompts and UI."""
    pressures = state.pressures if isinstance(state, ThreadState) else state
    active: list[tuple[str, float, str]] = []

    if pressures.suspicion >= 0.4:
        active.append(("suspicion", pressures.suspicion, "people are watching"))
    if pressures.scarcity >= 0.4:
        active.append(("scarcity", pressures.scarcity, "resources feel thin"))
    if pressures.wounds >= 0.4:
        active.append(("wounds", pressures.wounds, "the body is carrying damage"))
    if pressures.debt >= 0.4:
        active.append(("debt", pressures.debt, "favors or coin are owed"))
    if pressures.faction_heat >= 0.4:
        active.append(("faction heat", pressures.faction_heat, "organized power has noticed"))
    if pressures.omen >= 0.4:
        active.append(("omen", pressures.omen, "fate presses close"))
    if pressures.exploit_score >= 0.4:
        active.append(("exploit", pressures.exploit_score, "the world senses a pattern being abused"))

    active.sort(key=lambda item: item[1], reverse=True)
    parts = [f"{label} {value:.1f}: {desc}" for label, value, desc in active[:3]]

    if pressures.stability_streak >= 2:
        parts.append(
            f"stability streak {pressures.stability_streak}: control is starting to look brittle"
        )

    return "; ".join(parts) if parts else "No external pressure currently dominates the scene."


def salient_pressure_prompt(state: ThreadState) -> str:
    """Return a compact directive for choice generation."""
    pressures = state.pressures
    if pressures.suspicion >= 1.5:
        return "Answer suspicion: flee notice, face a witness, or redirect blame."
    if pressures.wounds >= 1.5:
        return "Answer wounds: bind yourself, rest, or seek aid."
    if pressures.debt >= 1.5:
        return "Answer debt: repay, bargain, or confront the one you owe."
    if pressures.scarcity >= 1.5:
        return "Answer scarcity: secure food, coin, or shelter."
    if pressures.faction_heat >= 1.5:
        return "Answer faction heat: placate authority, hide, or escape."
    if pressures.omen >= 1.5:
        return "Answer omen: heed, ward, or interpret the sign."

    active_oath = next(
        (o for o in state.soul_ledger.active_oaths if o.status == "active"),
        None,
    )
    if active_oath and active_oath.terms and active_oath.terms.price:
        return f"Answer oath cost: account for the price '{active_oath.terms.price}'."

    return ""


def apply_pressure_delta(
    pressures: PressureState,
    delta: dict[str, float],
    *,
    stable_turn: bool | None = None,
) -> PressureState:
    """Apply a pressure delta with clamping and streak updates."""
    updated = pressures.model_copy(deep=True)
    for key, value in delta.items():
        if not hasattr(updated, key):
            continue
        if key == "stability_streak":
            continue
        current = getattr(updated, key)
        setattr(updated, key, _clamp(current + value))

    if stable_turn is True:
        updated.stability_streak = min(updated.stability_streak + 1, 12)
    elif stable_turn is False:
        updated.stability_streak = 0

    return updated


def evolve_pressures(
    state: ThreadState,
    action: str,
    outcome: ResolvedOutcome,
    proposal_pressure: dict[str, float] | None = None,
) -> PressureEvolution:
    """Compute pressure changes for one resolved turn."""
    delta: dict[str, float] = {
        "suspicion": 0.0,
        "scarcity": 0.0,
        "wounds": 0.0,
        "debt": 0.0,
        "faction_heat": 0.0,
        "omen": 0.0,
        "exploit_score": 0.0,
    }

    normalized = _normalize_action(action)
    last_normalized = _normalize_action(state.last_action)

    violent = _contains_any(normalized, _VIOLENT_WORDS)
    deceptive = _contains_any(normalized, _DECEPTIVE_WORDS)
    public = _contains_any(normalized, _PUBLIC_WORDS)
    recovery = _contains_any(normalized, _RECOVERY_WORDS)
    resource = _contains_any(normalized, _RESOURCE_WORDS)
    payment = _contains_any(normalized, _PAYMENT_WORDS)
    cautious = _contains_any(normalized, _CAUTIOUS_WORDS)

    if violent:
        delta["wounds"] += 0.7
        delta["suspicion"] += 0.5
        delta["faction_heat"] += 0.4
    if deceptive:
        delta["suspicion"] += 0.6
        delta["exploit_score"] += 0.8
    if public:
        delta["suspicion"] += 0.4
        delta["faction_heat"] += 0.2
    if recovery:
        delta["wounds"] -= 0.8
    if resource:
        delta["scarcity"] += 0.5
        delta["debt"] += 0.2
    if payment:
        delta["debt"] -= 0.8
        delta["scarcity"] -= 0.3
    if cautious:
        delta["suspicion"] -= 0.2

    if last_normalized and normalized == last_normalized:
        delta["exploit_score"] += 1.0
    else:
        delta["exploit_score"] -= 0.25

    if outcome.nemesis_struck:
        delta["omen"] += 0.8
        delta["suspicion"] += 0.4
        delta["exploit_score"] += 0.6
    if outcome.eris_struck:
        delta["omen"] += 0.6
        delta["scarcity"] += 0.2
        delta["wounds"] += 0.2
    if outcome.prophecy_updated:
        delta["omen"] += 0.5
    if outcome.oath_broken:
        delta["suspicion"] += 1.2
        delta["faction_heat"] += 0.8
        delta["exploit_score"] += 1.0

    profile = state.soul_ledger.hamartia_profile
    if profile:
        social_bias = profile.social_cost_bias.lower()
        if "avoid" in social_bias and cautious:
            delta["suspicion"] += 0.4
            delta["faction_heat"] += 0.3
        if "public" in social_bias and public:
            delta["suspicion"] += 0.2

    if proposal_pressure:
        for key, value in proposal_pressure.items():
            if key in delta:
                delta[key] += value

    stable_turn = (
        not outcome.nemesis_struck
        and not outcome.eris_struck
        and not outcome.terminal
        and sum(abs(value) for value in delta.values()) < 1.5
    )

    delta = {
        key: round(value, 2)
        for key, value in delta.items()
        if abs(value) >= 0.05
    }

    projected = apply_pressure_delta(
        state.pressures,
        delta,
        stable_turn=stable_turn,
    )
    return PressureEvolution(
        delta=delta,
        stable_turn=stable_turn,
        summary=pressure_summary(projected),
    )
