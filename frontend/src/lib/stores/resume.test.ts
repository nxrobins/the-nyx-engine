import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { ThreadState } from '$lib/types/engine';
import {
	resumeGame,
	gameState,
	isInitialized,
	isTerminal,
	deathReason,
	uiChoices,
	proseHistory
} from './engine';

// The node test env has no localStorage; install a Map-backed stub.
function installLocalStorage(initial: Record<string, string> = {}) {
	const store = new Map(Object.entries(initial));
	(globalThis as unknown as { localStorage: Storage }).localStorage = {
		getItem: (k: string) => store.get(k) ?? null,
		setItem: (k: string, v: string) => void store.set(k, v),
		removeItem: (k: string) => void store.delete(k),
		clear: () => store.clear(),
		key: () => null,
		length: 0
	} as unknown as Storage;
	return store;
}

function mockResume(body: object, status = 200) {
	(globalThis as unknown as { fetch: typeof fetch }).fetch = vi.fn(async (url: string | URL) => {
		if (String(url).includes('/api/resume')) {
			return new Response(JSON.stringify(body), { status });
		}
		return new Response('[]', { status: 200 }); // plates etc. — void, self-catching
	}) as unknown as typeof fetch;
}

const restored = {
	session_id: 'sess-1',
	resume_token: 'tok-1',
	prose: 'you are mid-life',
	state: { session: { turn_count: 8 }, recent_traces: [] } as unknown as ThreadState,
	terminal: false,
	ui_choices: ['reach out', 'stay still']
};

beforeEach(() => {
	gameState.set(null);
	isInitialized.set(false);
	isTerminal.set(false);
	deathReason.set('');
	uiChoices.set([]);
});

afterEach(() => {
	vi.restoreAllMocks();
	delete (globalThis as unknown as { localStorage?: Storage }).localStorage;
});

describe('resumeGame — durability sub-slice 4', () => {
	it('returns false and does not fetch when no token is stored', async () => {
		installLocalStorage({});
		const fetchSpy = vi.fn();
		(globalThis as unknown as { fetch: typeof fetch }).fetch = fetchSpy as unknown as typeof fetch;
		expect(await resumeGame()).toBe(false);
		expect(fetchSpy).not.toHaveBeenCalled();
	});

	it('restores a living thread from the stored token', async () => {
		installLocalStorage({ nyx_resume_token: 'tok-1' });
		mockResume(restored);
		expect(await resumeGame()).toBe(true);
		expect(get(isInitialized)).toBe(true);
		expect((get(gameState) as unknown as { session: { turn_count: number } }).session.turn_count).toBe(8);
		expect(get(uiChoices)).toEqual(['reach out', 'stay still']);
	});

	it('clears the token and returns false when unrestorable (404)', async () => {
		const store = installLocalStorage({ nyx_resume_token: 'stale' });
		mockResume({}, 404);
		expect(await resumeGame()).toBe(false);
		expect(store.get('nyx_resume_token')).toBeUndefined(); // start fresh next boot
	});

	it('keeps the token on a transient 500 (retry next boot), returns false', async () => {
		// V2-MED: a 500 is not proof the life is gone — a DB hiccup or a deploy
		// restart mid-request 500s too. Clearing the token here would permanently
		// orphan a resumable life. Only 404 (unknown/stale) is unrestorable.
		const store = installLocalStorage({ nyx_resume_token: 'tok-live' });
		mockResume({}, 500);
		expect(await resumeGame()).toBe(false);
		expect(store.get('nyx_resume_token')).toBe('tok-live');
	});

	it('does not stomp a new life started during the in-flight resume (V2-MED)', async () => {
		// The boot race: onMount awaits resumeGame() while the player clicks
		// "awaken" — initGame commits a fresh session (isInitialized = true).
		// The late-resolving resume must YIELD, not overwrite the new life.
		installLocalStorage({ nyx_resume_token: 'tok-old' });
		isInitialized.set(true);
		const freshState = { session: { turn_count: 1 }, recent_traces: [] } as unknown as ThreadState;
		gameState.set(freshState);
		proseHistory.set(['a new life begins']);
		mockResume(restored); // the OLD thread (turn 8) comes back late

		expect(await resumeGame()).toBe(false);      // defer to the new life
		expect(get(gameState)).toBe(freshState);     // NOT stomped
		expect(get(proseHistory)).toEqual(['a new life begins']);
	});

	it('resumes a terminal thread into the death state (SC-6/UP-4)', async () => {
		installLocalStorage({ nyx_resume_token: 'tok-dead' });
		mockResume({ ...restored, terminal: true, death_reason: 'You chose oblivion.', epitaph: 'He burned bright.' });
		expect(await resumeGame()).toBe(true);
		expect(get(isTerminal)).toBe(true);
		expect(get(deathReason)).toBe('You chose oblivion.');
	});
});
