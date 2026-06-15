import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { ThreadState, CrisisResources } from '$lib/types/engine';
import {
	handleStreamEvent,
	submitAction,
	gameState,
	isTerminal,
	isProcessing,
	proseHistory,
	streamingProse,
	uiChoices,
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

/** Build a mock fetch Response whose body streams the given raw chunks — the
 *  chunk boundaries are deliberately caller-controlled so a frame can be split
 *  across two reads (the buffering torture test). */
function streamResponse(chunks: string[], ok = true): Response {
	const encoder = new TextEncoder();
	const body = new ReadableStream<Uint8Array>({
		start(controller) {
			for (const c of chunks) controller.enqueue(encoder.encode(c));
			controller.close();
		}
	});
	return { ok, body } as unknown as Response;
}

const frame = (obj: unknown) => `data: ${JSON.stringify(obj)}\n\n`;
const minimalState = { session: { turn_count: 1 } } as unknown as ThreadState;

describe('submitAction — the 3-phase SSE stream → store pipeline', () => {
	beforeEach(() => {
		proseHistory.set([]);
		streamingProse.set('');
		gameState.set(null);
		uiChoices.set([]);
		isProcessing.set(false);
		isTerminal.set(false);
		vi.spyOn(console, 'error').mockImplementation(() => {});
		vi.spyOn(console, 'warn').mockImplementation(() => {});
	});
	afterEach(() => vi.restoreAllMocks());

	it('a full mechanic→prose→state→done run commits prose and lands the state', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
			frame({ type: 'mechanic', payload: {} }),
			frame({ type: 'prose', text: 'The ' }),
			frame({ type: 'prose', text: 'blade falls.' }),
			frame({ type: 'state', payload: minimalState, ui_choices: ['run', 'fight'], terminal: false }),
			frame({ type: 'done' })
		])));

		await submitAction('strike');

		expect(get(proseHistory)).toEqual(['The blade falls.']); // committed once, in order
		expect(get(gameState)).toEqual(minimalState);
		expect(get(uiChoices)).toEqual(['run', 'fight']);
		expect(get(isProcessing)).toBe(false); // control handed back
		expect(get(streamingProse)).toBe(''); // drained on commit
	});

	it('reassembles a frame split across chunk boundaries (no partial-JSON crash)', async () => {
		// The prose frame is torn mid-JSON across two reads.
		vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
			'data: {"type":"pro',
			'se","text":"reassembled"}\n\n' + frame({ type: 'done' })
		])));

		await submitAction('strike');

		// The split frame parsed correctly; with no state frame, the finally
		// safety-net commits the orphaned prose so it is not lost.
		expect(get(proseHistory)).toEqual(['reassembled']);
		expect(get(isProcessing)).toBe(false);
	});

	it('a malformed frame is swallowed and the stream keeps processing', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => streamResponse([
			'data: {bad json here\n\n',
			frame({ type: 'prose', text: 'survived' }),
			frame({ type: 'state', payload: minimalState, ui_choices: [], terminal: false })
		])));

		await submitAction('strike');

		expect(get(proseHistory)).toEqual(['survived']); // the good frame still landed
		expect(get(gameState)).toEqual(minimalState);
	});

	it('a failed connection clears the processing flag and throws', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => streamResponse([], false)));
		await expect(submitAction('strike')).rejects.toThrow();
		expect(get(isProcessing)).toBe(false); // never stuck
	});
});
