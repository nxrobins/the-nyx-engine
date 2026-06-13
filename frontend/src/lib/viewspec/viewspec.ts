/**
 * THE TELL — the ViewSpec IR.
 *
 * Generalizes the Ink's pattern (state → clamped derivations → ambient visuals)
 * into a renderer-AGNOSTIC composition spec. The screen reacts to charged
 * moments: the prose flinches at the blow then settles to pristine, and the
 * room stays colored by what happened.
 *
 * The IR emits INTENT, not CSS (VS-E6) — semantic fields a Svelte/CSS layer
 * maps to custom properties today, and a future canvas/glyph emitter could
 * consume unchanged. It is the forward-seam, built cheap.
 *
 * The laws (full matrix in the plan):
 *   VS-E1  Total over every reachable state — null → identity ViewSpec, no throw.
 *   VS-E4  Every numeric clamped [0,1] (NaN/Inf → 0).
 *   VS-E6  Emits intent, not CSS (the lone CSS string is weather's `tint`).
 *   VS-E11 No false dominance — soulVector='' unless the leader clears the
 *          field by ≥ 1.0 on the 0–10 scale; ties resolve to neutral.
 *   VS-E15 Pure, total, deterministic in (state, lastEvent, prevDoomStage) —
 *          no time/random, no hidden mutable read. prevDoomStage is a
 *          PARAMETER (the consumer holds the delta), never read from state.
 */

import type { ThreadState, MechanicEvent } from '$lib/types/engine';
import { deriveWeather, doomIntensity, omenTurbulence, type InkWeather } from '$lib/utils/weather';

export type FlinchAgent = 'none' | 'nemesis' | 'eris' | 'atropos' | 'momus';

/** A ONE-SHOT entrance treatment for the prose region. Never steady-state. */
export interface FlinchSpec {
	agent: FlinchAgent;
	intensity: number; // 0..1
	oneShot: true;
}

/** Steady-state composition of the room — the Ink, plus soul grammar. */
export interface AmbientSpec extends InkWeather {
	soulVector: string; // 'metis'|'bia'|'kleos'|'aidos'|'' (argmax, only if it clears the field)
	soulBias: number; // 0..1 — how far the leader stands above the mean
	lastIntervention: string; // 'nemesis'|'eris'|'' — the room's lingering memory
}

export interface ViewSpec {
	ambient: AmbientSpec;
	flinch: FlinchSpec;
}

const NONE: FlinchSpec = { agent: 'none', intensity: 0, oneShot: true };

/** Clamp to [0,1]; NaN/Infinity collapse to 0 (VS-E4). Local copy — weather's
 *  is private and weather.ts stays untouched. */
function clamp01(x: number): number {
	return Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0;
}

/** The dominant soul vector, only when it genuinely leads (VS-E11). A 4-way
 *  tie (the Unformed opening) returns '' — no false dominance, no array order. */
export function dominantSoulVector(state: ThreadState | null): { vector: string; bias: number } {
	const v = state?.soul_ledger?.vectors;
	if (!v) return { vector: '', bias: 0 };
	const entries: [string, number][] = [
		['metis', v.metis],
		['bia', v.bia],
		['kleos', v.kleos],
		['aidos', v.aidos],
	].map(([k, n]) => [k as string, Number.isFinite(n as number) ? (n as number) : 0]);
	entries.sort((a, b) => b[1] - a[1]);
	const [topK, topV] = entries[0];
	const secondV = entries[1][1];
	if (topV - secondV < 1.0) return { vector: '', bias: 0 }; // ties/near-ties → neutral
	const mean = entries.reduce((s, [, n]) => s + n, 0) / entries.length;
	return { vector: topK, bias: clamp01((topV - mean) / 5) };
}

/** Which intervention the room remembers — read from the committed trace so it
 *  persists across the turn (unlike the 2.5s mechanic toast). */
function lastIntervention(state: ThreadState | null): string {
	const order = state?.recent_traces?.at(-1)?.winner_order ?? [];
	if (order.includes('nemesis')) return 'nemesis';
	if (order.includes('eris')) return 'eris';
	return '';
}

/**
 * The transient flinch. Charged events surface at two times: nemesis/eris/
 * invalid ride the `mechanic` event (lastEvent); atropos/doom-advance are only
 * knowable at the `state` commit (doom-stage delta vs prevDoomStage, or the
 * trace naming atropos). One flinch, highest priority wins.
 */
export function deriveFlinch(
	state: ThreadState | null,
	lastEvent?: MechanicEvent | null,
	prevDoomStage?: number | null
): FlinchSpec {
	if (lastEvent?.nemesis_struck) {
		return { agent: 'nemesis', intensity: clamp01(0.6 + 0.4 * doomIntensity(state)), oneShot: true };
	}
	if (lastEvent?.eris_struck) {
		return { agent: 'eris', intensity: clamp01(0.5 + 0.3 * omenTurbulence(state)), oneShot: true };
	}
	const doom = state?.doom;
	const stageAdvanced =
		!!doom?.active &&
		prevDoomStage !== null &&
		prevDoomStage !== undefined &&
		(doom.stage ?? 0) > prevDoomStage;
	const atroposCut = (state?.recent_traces?.at(-1)?.winner_order ?? []).includes('atropos');
	if (stageAdvanced || atroposCut) {
		const di = doomIntensity(state);
		return { agent: 'atropos', intensity: clamp01(di > 0 ? di : 0.6), oneShot: true };
	}
	if (lastEvent && lastEvent.valid === false) {
		return { agent: 'momus', intensity: 0.5, oneShot: true };
	}
	return NONE;
}

/** The steady-state half — the Ink, plus the soul grammar and the room's memory. */
export function deriveAmbient(state: ThreadState | null): AmbientSpec {
	const { vector, bias } = dominantSoulVector(state);
	return {
		...deriveWeather(state),
		soulVector: vector,
		soulBias: bias,
		lastIntervention: lastIntervention(state),
	};
}

/** The whole spec. Null → identity (calm ambient + no flinch). Pure, total. */
export function deriveViewSpec(
	state: ThreadState | null,
	lastEvent?: MechanicEvent | null,
	prevDoomStage?: number | null
): ViewSpec {
	return {
		ambient: deriveAmbient(state),
		flinch: deriveFlinch(state, lastEvent, prevDoomStage),
	};
}
