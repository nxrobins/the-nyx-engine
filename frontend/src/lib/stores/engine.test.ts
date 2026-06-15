import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import type { ThreadState, CrisisResources } from '$lib/types/engine';
import {
	handleStreamEvent,
	gameState,
	isTerminal,
	proseHistory,
	streamingProse,
	crisisInterstitial
} from './engine';

// A recognizable pre-existing game state — if a crisis frame mutated it, the
// reference check below would fail.
const liveState = { session: { turn_count: 4 } } as unknown as ThreadState;
const resources = {
	disclaimer: 'This is a game; these are real, independent services.',
	lifelines: [{ label: '988', detail: 'call or text' }]
} as unknown as CrisisResources;

beforeEach(() => {
	// Manual reset (resetGame() does a network fetch, unusable in a unit test).
	gameState.set(liveState);
	isTerminal.set(false);
	proseHistory.set(['an earlier turn']);
	streamingProse.set('');
	crisisInterstitial.set(null);
});

describe('handleStreamEvent — the Vigil SAFE-C9 invariant', () => {
	it('a crisis_resources frame opens the card WITHOUT touching game state', () => {
		handleStreamEvent({ type: 'crisis_resources', payload: resources });

		// The help card is shown…
		expect(get(crisisInterstitial)).toEqual(resources);
		// …and nothing about the in-fiction turn is disturbed: the death still
		// resolves on its own state frame, prose is not committed early, control
		// is not handed back. (The exact same-reference check is the strong form.)
		expect(get(gameState)).toBe(liveState);
		expect(get(isTerminal)).toBe(false);
		expect(get(proseHistory)).toEqual(['an earlier turn']);
	});

	it('a payload-less crisis frame is an inert no-op (never a blank card)', () => {
		handleStreamEvent({ type: 'crisis_resources', payload: null });
		expect(get(crisisInterstitial)).toBeNull();
		expect(get(gameState)).toBe(liveState);
	});

	it('control: a prose frame DOES mutate its store (the guard is not vacuous)', () => {
		// Proves handleStreamEvent can mutate stores at all — so the "untouched"
		// assertions above are meaningful, not a false pass.
		handleStreamEvent({ type: 'prose', text: 'the blade falls' });
		expect(get(streamingProse)).toBe('the blade falls');
		expect(get(crisisInterstitial)).toBeNull(); // a prose frame is not a crisis
	});
});
