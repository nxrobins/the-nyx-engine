/**
 * Nyx Engine v2.0 — Reactive Game State Store
 *
 * Manages: thread state, prose history, Hypnos stream, BFL background,
 * SSE connection lifecycle, and the Turn 0 init flow.
 */

import { writable } from 'svelte/store';
import type { ThreadState, TurnResult, HamartiaOptions } from '$lib/types/engine';
import { vestibuleState } from '$lib/stores/vestibule';

// ── Core State ──────────────────────────────────────────────────

/** Current thread state (null before Turn 0 init) */
export const gameState = writable<ThreadState | null>(null);

/** Prose history — array of turn prose strings */
export const proseHistory = writable<string[]>([]);

/** Current Hypnos filler stream (cleared on Clotho handoff) */
export const hypnosStream = writable<string>('');

/** Whether the engine is mid-turn */
export const isProcessing = writable<boolean>(false);

/** Whether the game has ended (Atropos severed the thread) */
export const isTerminal = writable<boolean>(false);

/** Death reason if terminal */
export const deathReason = writable<string>('');

/** BFL milestone image URL (displayed as background in TheThread) */
export const backgroundImage = writable<string>('');

/** Whether Turn 0 init has completed (gates the three-pane view) */
export const isInitialized = writable<boolean>(false);

/** Epoch choice buttons (empty in Phase 4 / open mode) */
export const uiChoices = writable<string[]>([]);

// ── Turn 0: Initialize Session ──────────────────────────────────

/**
 * Fetch available hamartia options from the backend.
 */
export async function fetchHamartiaOptions(): Promise<string[]> {
	const res = await fetch('/api/hamartia-options');
	if (!res.ok) throw new Error('Failed to fetch hamartia options');
	const data: HamartiaOptions = await res.json();
	return data.options;
}

/**
 * Initialize a new game session with player identity.
 * Calls POST /init and sets up state for Turn 1+.
 */
export async function initGame(params: {
	player_id: string;
	name: string;
	gender: string;
	hamartia: string;
	first_memory: string;
}): Promise<TurnResult> {
	const res = await fetch('/api/init', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(params),
	});

	if (!res.ok) throw new Error('Initialization failed');

	const result: TurnResult = await res.json();

	gameState.set(result.state);
	proseHistory.set([result.prose]);
	uiChoices.set(result.ui_choices || []);
	isInitialized.set(true);

	return result;
}

// ── Turn 1+: SSE Action Submission ──────────────────────────────

/**
 * Submit a player action via the SSE stream endpoint.
 *
 * Implements the Hypnos Mask protocol:
 *   1. Stream Hypnos filler fragments immediately
 *   2. On 'result' event: fade out Hypnos, fade in Clotho prose
 *   3. On 'image' event: set BFL background image
 *   4. On 'done': close connection
 *
 * Heartbeat events are silently ignored (keep-alive for BFL polling).
 */
export async function submitAction(action: string): Promise<void> {
	isProcessing.set(true);
	hypnosStream.set('');

	const url = `/api/stream?action=${encodeURIComponent(action)}`;
	const eventSource = new EventSource(url);

	return new Promise<void>((resolve, reject) => {
		// Hypnos filler fragments — append as they arrive
		eventSource.addEventListener('hypnos', (e) => {
			const data = JSON.parse(e.data);
			hypnosStream.update((current) =>
				current + (current ? '\n\n' : '') + data.text
			);
		});

		// Final Clotho result — replaces Hypnos
		eventSource.addEventListener('result', (e) => {
			const result: TurnResult = JSON.parse(e.data);

			// Clear Hypnos stream, push final prose
			hypnosStream.set('');
			proseHistory.update((h) => [...h, result.prose]);
			gameState.set(result.state);
			uiChoices.set(result.ui_choices || []);

			if (result.terminal) {
				isTerminal.set(true);
				deathReason.set(result.death_reason);
			}
		});

		// BFL milestone image
		eventSource.addEventListener('image', (e) => {
			const data = JSON.parse(e.data);
			if (data.url) {
				backgroundImage.set(data.url);
			}
		});

		// Heartbeat — keep-alive while BFL polls (ignore silently)
		eventSource.addEventListener('heartbeat', () => {
			// Intentionally empty — connection stays open
		});

		// Stream complete
		eventSource.addEventListener('done', () => {
			eventSource.close();
			isProcessing.set(false);
			resolve();
		});

		// Error handler
		eventSource.onerror = () => {
			eventSource.close();
			isProcessing.set(false);
			reject(new Error('Connection to the Nyx Engine lost.'));
		};
	});
}

// ── Reset ───────────────────────────────────────────────────────

/**
 * Reset the game session. Returns to hamartia selection screen.
 */
export async function resetGame(): Promise<void> {
	await fetch('/api/reset', { method: 'POST' });
	gameState.set(null);
	proseHistory.set([]);
	hypnosStream.set('');
	backgroundImage.set('');
	isProcessing.set(false);
	isTerminal.set(false);
	deathReason.set('');
	uiChoices.set([]);
	isInitialized.set(false);
	vestibuleState.set('title');
}
