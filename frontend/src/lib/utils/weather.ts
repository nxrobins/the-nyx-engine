/**
 * THE INK — state-as-weather derivations.
 *
 * Pure math from ThreadState to ambient ink behavior. No DOM, no stores.
 * The screen is the Hubris Index: omen roils the ink, doom bleeds from the
 * edges, wounds and faction heat deepen the pool, the epoch tints the wash.
 *
 * INK-E1: total over every reachable state — null state, null doom, missing
 * pressures all yield calm. INK-E4: every numeric output is clamped to [0,1]
 * (NaN → 0) so an out-of-range value can never reach CSS.
 */

import type { ThreadState } from '$lib/types/engine';

export interface InkWeather {
	/** 0..1 — omen-driven drift of the ink wisps */
	turbulence: number;
	/** 0..1 — doom stage progress; bleeds the frame dark */
	doom: number;
	/** 0..1 — wounds / faction heat; deepens the edge vignette */
	edge: number;
	/** rgba() wash for the current epoch (alpha ≤ 0.08 — INK-E4 budget) */
	tint: string;
}

/** Clamp to [0,1]; NaN/Infinity collapse to 0 (INK-E4). */
function clamp01(x: number): number {
	return Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0;
}

/** Omen pressure (0–10 scale) → turbulence. Visible from ~1, saturates at 6. */
export function omenTurbulence(state: ThreadState | null): number {
	const omen = state?.pressures?.omen ?? 0;
	return clamp01(omen / 6);
}

/** Doom stage progress. Inactive or malformed doom → 0. */
export function doomIntensity(state: ThreadState | null): number {
	const doom = state?.doom;
	if (!doom?.active) return 0;
	const max = doom.max_stage ?? 0;
	if (max <= 0) return 0;
	return clamp01((doom.stage ?? 0) / max);
}

/** Edge darkening from the body's pressures (wounds, faction heat; 0–10). */
export function edgeDarkening(state: ThreadState | null): number {
	const wounds = state?.pressures?.wounds ?? 0;
	const heat = state?.pressures?.faction_heat ?? 0;
	return clamp01(Math.max(wounds, heat) / 10);
}

/** Epoch wash — hearth gold, waning grey, cold indigo, ashen oxblood. */
const EPOCH_TINTS: Record<number, string> = {
	1: 'rgba(184, 134, 11, 0.05)',
	2: 'rgba(150, 150, 160, 0.04)',
	3: 'rgba(99, 102, 141, 0.05)',
	4: 'rgba(120, 40, 40, 0.05)',
};

export function epochTint(state: ThreadState | null): string {
	const phase = state?.session?.epoch_phase ?? 1;
	return EPOCH_TINTS[phase] ?? EPOCH_TINTS[1];
}

/** Compose the full weather. Null state → calm (the fallback identity). */
export function deriveWeather(state: ThreadState | null): InkWeather {
	return {
		turbulence: omenTurbulence(state),
		doom: doomIntensity(state),
		edge: edgeDarkening(state),
		tint: epochTint(state),
	};
}
