/**
 * Nyx Engine v3.0 — Reactive Game State Store (Sprint 6: Streaming)
 *
 * Manages: thread state, prose history, streaming prose, mechanic toast,
 * BFL background, SSE connection lifecycle, and the Turn 0 init flow.
 *
 * v3.0 changes:
 * - submitAction() uses fetch + ReadableStream (replaces EventSource)
 * - New stores: streamingProse (typewriter), mechanicToast (flash)
 * - 3-Phase SSE protocol: mechanic → prose → state
 * - Buffer-split on \n\n boundaries for safe JSON.parse
 */

import { writable } from 'svelte/store';
import type {
	ThreadState,
	TurnResult,
	HamartiaOptions,
	MechanicEvent,
	DeliberationTrace
} from '$lib/types/engine';
import { vestibuleState } from '$lib/stores/vestibule';

// ── Session ID ──────────────────────────────────────────────────

/** Session UUID returned by POST /init, sent on every subsequent request. */
let _sessionId = '';

/** Read-only accessor for components that need to display session info. */
export function getSessionId(): string {
	return _sessionId;
}

// ── Core State ──────────────────────────────────────────────────

/** Current thread state (null before Turn 0 init) */
export const gameState = writable<ThreadState | null>(null);

/** Prose history — array of turn prose strings */
export const proseHistory = writable<string[]>([]);

/** Streaming prose — accumulates tokens during Clotho typewriter phase */
export const streamingProse = writable<string>('');

/** Mechanic toast — flashed on screen after Lachesis math resolves */
export const mechanicToast = writable<MechanicEvent | null>(null);
export const deliberationTrace = writable<DeliberationTrace | null>(null);
export const repairWitness = writable<string | null>(null);

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

/** Dream interlude text from Hypnos (displayed as full-screen overlay) */
export const activeDream = writable<string>('');

/** Dismiss the dream overlay — called by [ Awaken ] button */
export function dismissDream(): void {
	activeDream.set('');
}

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

	_sessionId = result.session_id;
	if (!_sessionId) {
		console.error('[nyx] CRITICAL: No session_id in /init response!', Object.keys(result));
	}
	gameState.set(result.state);
	proseHistory.set([result.prose]);
	uiChoices.set(result.ui_choices || []);
	deliberationTrace.set(result.state.recent_traces?.at(-1) ?? null);
	repairWitness.set(null);
	isInitialized.set(true);

	return result;
}

// ── Turn 1+: Streaming Action Submission ─────────────────────────

/**
 * Submit a player action via the 3-Phase streaming pipeline.
 *
 * Uses fetch + ReadableStream (replaces EventSource GET):
 *   Phase 1: mechanic — Lachesis math + conflict resolution
 *   Phase 2: prose    — Clotho tokens for typewriter effect
 *   Phase 3: state    — Final state + choices + cleanup
 *
 * Buffer-splits on \n\n boundaries to prevent partial JSON.parse crashes.
 */
export async function submitAction(action: string): Promise<void> {
	isProcessing.set(true);
	streamingProse.set('');
	mechanicToast.set(null);
	deliberationTrace.set(null);
	repairWitness.set(null);
	uiChoices.set([]);
	activeDream.set('');

	const response = await fetch('/api/turn', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ action, session_id: _sessionId }),
	});

	if (!response.ok || !response.body) {
		isProcessing.set(false);
		throw new Error('Connection to the Nyx Engine lost.');
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder('utf-8');
	let buffer = '';
	let fullProse = '';

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });

			// Split strictly on \n\n boundaries
			let boundary = buffer.indexOf('\n\n');
			while (boundary !== -1) {
				const chunk = buffer.slice(0, boundary).trim();
				buffer = buffer.slice(boundary + 2);
				boundary = buffer.indexOf('\n\n');

				if (chunk.startsWith('data: ')) {
					try {
						const data = JSON.parse(chunk.slice(6));
						handleStreamEvent(data);
						if (data.type === 'prose') {
							fullProse += data.text;
						}
					} catch (e) {
						console.error('[nyx] SSE parse error:', e, 'chunk:', chunk.slice(0, 200));
					}
				}
			}
		}

		// Flush any remaining buffer
		if (buffer.trim().startsWith('data: ')) {
			try {
				const data = JSON.parse(buffer.trim().slice(6));
				handleStreamEvent(data);
				if (data.type === 'prose') {
					fullProse += data.text;
				}
			} catch (e) {
				console.error('[nyx] SSE flush parse error:', e, 'buffer:', buffer.slice(0, 200));
			}
		}
	} finally {
		reader.releaseLock();

		// Safety net: if the 'state' event was dropped, commit any orphaned
		// streaming prose so paragraphs don't repeat from the previous turn.
		let orphanedProse = '';
		streamingProse.update((current) => {
			orphanedProse = current;
			return '';
		});
		if (orphanedProse) {
			console.warn('[nyx] State event missed — committing orphaned streaming prose');
			proseHistory.update((h) => [...h, orphanedProse]);
		}

		// Ensure processing flag is always cleared so UI is never stuck
		isProcessing.set(false);
	}
}

/**
 * Route a parsed SSE event to the appropriate store update.
 */
function handleStreamEvent(data: Record<string, unknown>): void {
	switch (data.type) {
		case 'mechanic': {
			const payload = data.payload as MechanicEvent;
			mechanicToast.set(payload);
			// Auto-clear toast after 2.5s
			setTimeout(() => mechanicToast.set(null), 2500);
			break;
		}

		case 'deliberation': {
			const payload = data.payload as DeliberationTrace;
			deliberationTrace.set(payload);
			break;
		}

		case 'prose_repair': {
			const text = data.text as string;
			streamingProse.set(text);
			repairWitness.set('Momus stripped contradiction from the weave before it could set.');
			break;
		}

		case 'prose': {
			const text = data.text as string;
			streamingProse.update((current) => current + text);
			break;
		}

		case 'state': {
			const payload = data.payload as ThreadState;
			const choices = (data.ui_choices as string[]) || [];
			const terminal = data.terminal as boolean;
			const death = (data.death_reason as string) || '';

			// Commit streaming prose to history
			let finalProse = '';
			streamingProse.update((current) => {
				finalProse = current;
				return '';
			});

			if (finalProse) {
				proseHistory.update((h) => [...h, finalProse]);
			}

			gameState.set(payload);
			deliberationTrace.set(payload.recent_traces?.at(-1) ?? null);
			uiChoices.set(choices);

			if (terminal) {
				isTerminal.set(true);
				deathReason.set(death);
			}

			// Player regains control on state event
			isProcessing.set(false);
			break;
		}

		case 'image': {
			const url = data.url as string;
			if (url) {
				backgroundImage.set(url);
			}
			break;
		}

		case 'dream': {
			const dreamText = data.text as string;
			if (dreamText) {
				activeDream.set(dreamText);
			}
			break;
		}

		case 'done': {
			// Stream fully complete — commit any orphaned prose before clearing
			let doneProse = '';
			streamingProse.update((current) => {
				doneProse = current;
				return '';
			});
			if (doneProse) {
				console.warn('[nyx] Done event fired with uncommitted prose — state event was dropped');
				proseHistory.update((h) => [...h, doneProse]);
			}
			isProcessing.set(false);
			break;
		}
	}
}

// ── Reset ───────────────────────────────────────────────────────

/**
 * Reset the game session. Returns to title screen.
 */
export async function resetGame(): Promise<void> {
	await fetch('/api/reset', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ action: '', session_id: _sessionId }),
	});
	_sessionId = '';
	gameState.set(null);
	proseHistory.set([]);
	streamingProse.set('');
	mechanicToast.set(null);
	deliberationTrace.set(null);
	repairWitness.set(null);
	backgroundImage.set('');
	isProcessing.set(false);
	isTerminal.set(false);
	deathReason.set('');
	uiChoices.set([]);
	activeDream.set('');
	isInitialized.set(false);
	vestibuleState.set('title');
}
