import { describe, it, expect } from 'vitest';
import type { ThreadState, SceneClock } from '$lib/types/engine';
import { deriveActiveClocks } from './clocks';

const clock = (p: Partial<SceneClock> & { clock_id: string; label: string }): SceneClock =>
	({ progress: 0, max_segments: 4, stakes: '', resolution_hint: '', lethal: false, ...p }) as SceneClock;

const st = (active: string[], ...clocks: SceneClock[]): ThreadState =>
	({
		canon: {
			clocks: Object.fromEntries(clocks.map((c) => [c.clock_id, c])),
			current_scene: { active_clock_ids: active }
		}
	}) as unknown as ThreadState;

describe('deriveActiveClocks', () => {
	it('is empty and never throws on null / canon-less / scene-less state', () => {
		expect(deriveActiveClocks(null)).toEqual([]);
		expect(deriveActiveClocks({} as ThreadState)).toEqual([]);
		expect(deriveActiveClocks({ canon: { current_scene: null } } as unknown as ThreadState)).toEqual([]);
	});

	it('returns only the clocks the current scene actually tracks', () => {
		const s = st(['a'], clock({ clock_id: 'a', label: 'A' }), clock({ clock_id: 'b', label: 'B' }));
		expect(deriveActiveClocks(s).map((c) => c.id)).toEqual(['a']); // 'b' is not active
	});

	it('skips a stale active id with no matching clock', () => {
		const s = st(['a', 'ghost'], clock({ clock_id: 'a', label: 'A' }));
		expect(deriveActiveClocks(s).map((c) => c.id)).toEqual(['a']);
	});

	it('computes remaining and clamps progress into [0, max]', () => {
		const s = st(['a'], clock({ clock_id: 'a', label: 'A', progress: 9, max_segments: 4 }));
		const [c] = deriveActiveClocks(s);
		expect(c.progress).toBe(4); // clamped
		expect(c.max).toBe(4);
		expect(c.remaining).toBe(0);
	});

	it('orders most-imminent first, then further-advanced', () => {
		const s = st(
			['far', 'near', 'tie'],
			clock({ clock_id: 'far', label: 'Far', progress: 1, max_segments: 6 }), // remaining 5
			clock({ clock_id: 'near', label: 'Near', progress: 3, max_segments: 4 }), // remaining 1
			clock({ clock_id: 'tie', label: 'Tie', progress: 5, max_segments: 6 }) // remaining 1, more progress
		);
		expect(deriveActiveClocks(s).map((c) => c.label)).toEqual(['Tie', 'Near', 'Far']);
	});

	it('carries stakes and the lethal flag', () => {
		const s = st(['a'], clock({ clock_id: 'a', label: 'A', stakes: 'the manhunt closes', lethal: true }));
		const [c] = deriveActiveClocks(s);
		expect(c.stakes).toBe('the manhunt closes');
		expect(c.lethal).toBe(true);
	});
});
