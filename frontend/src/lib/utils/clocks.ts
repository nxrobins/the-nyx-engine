/**
 * WHAT CLOSES IN — the world's countdowns, made legible.
 *
 * Pure derivation from ThreadState to the active scene clocks: the ticking
 * threats that, ignored, spike pressure, seal dooms, and (The World Takes) claim
 * the people around you. Until now they advanced only in prose — the player
 * never saw the sand running out.
 *
 * Total over every reachable state (null / canon-less / no scene → empty, never
 * throws). Only clocks the current scene actually tracks are returned, ordered
 * most-imminent first. No DOM, no stores — unit-testable.
 */

import type { ThreadState, SceneClock } from '$lib/types/engine';

export interface ClockView {
	id: string;
	label: string;
	progress: number;
	max: number;
	/** segments left before it runs out */
	remaining: number;
	stakes: string;
	lethal: boolean;
}

export function deriveActiveClocks(state: ThreadState | null): ClockView[] {
	const canon = state?.canon;
	const scene = canon?.current_scene;
	if (!canon || !scene) return [];

	const out: ClockView[] = [];
	for (const id of scene.active_clock_ids ?? []) {
		const c: SceneClock | undefined = canon.clocks?.[id];
		if (!c) continue; // a stale id with no clock is silently skipped
		const max = Math.max(1, c.max_segments);
		const progress = Math.min(Math.max(0, c.progress), max);
		out.push({
			id: c.clock_id,
			label: c.label,
			progress,
			max,
			remaining: max - progress,
			stakes: c.stakes,
			lethal: c.lethal
		});
	}

	// Most imminent first; among equally-close, the further-advanced clock leads.
	out.sort((a, b) => a.remaining - b.remaining || b.progress - a.progress);
	return out;
}
