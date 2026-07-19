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

import { get, writable } from 'svelte/store';
import type {
	ThreadState,
	TurnResult,
	HamartiaOptions,
	MechanicEvent,
	DeliberationTrace,
	CrisisResources
} from '$lib/types/engine';
import { vestibuleState, currentContentPrefs } from '$lib/stores/vestibule';
import { clearPlates, loadPlates, plateManifest, scenePlateUrl } from '$lib/stores/plates';
import { deriveFlinch, type FlinchAgent } from '$lib/viewspec/viewspec';

// ── Session ID ──────────────────────────────────────────────────

/** Session UUID returned by POST /init, sent on every subsequent request. */
let _sessionId = '';

/** Read-only accessor for components that need to display session info. */
export function getSessionId(): string {
	return _sessionId;
}

// ── Durability: the resume token (THE THREAD PERSISTS, sub-slice 4) ──
// A session UUID is ephemeral; the resume token, persisted here, is what lets a
// living thread survive a refresh / new tab / restart. Distinct from player_id.
const RESUME_TOKEN_KEY = 'nyx_resume_token';

function saveResumeToken(token: string | undefined): void {
	if (typeof localStorage === 'undefined' || !token) return;
	try {
		localStorage.setItem(RESUME_TOKEN_KEY, token);
	} catch {
		/* private-mode / quota — durability degrades to in-session only */
	}
}

function clearResumeToken(): void {
	if (typeof localStorage === 'undefined') return;
	try {
		localStorage.removeItem(RESUME_TOKEN_KEY);
	} catch {
		/* ignore */
	}
}

export function getStoredResumeToken(): string {
	if (typeof localStorage === 'undefined') return '';
	try {
		return localStorage.getItem(RESUME_TOKEN_KEY) || '';
	} catch {
		return '';
	}
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

/** The Witness: the carved epitaph, delivered with the death event */
export const epitaph = writable<string>('');

/** The Witness: the bound life's book id ('' = this life went unbound) */
export const bookId = writable<string>('');

/** BFL milestone image URL (displayed as background in TheThread) */
export const backgroundImage = writable<string>('');

/** The Ink: where the player stood when the milestone image arrived.
    The milestone holds while they remain in the scene it crowned, then
    yields back to the world's plate on scene change (or a dream) — but
    only when a plate exists to resume to (plateless worlds keep the
    persist-until-death behavior). Null when unknowable: the milestone
    holds (INK-E1 — a null scene is never a scene change). */
let _milestoneLocationId: string | null = null;

/** Clear the milestone if the scene moved on and a plate can resume. */
function yieldMilestoneIfSceneChanged(state: ThreadState | null): void {
	if (!get(backgroundImage)) return;
	const loc = state?.canon?.current_scene?.location_id ?? null;
	const moved =
		_milestoneLocationId !== null && loc !== null && loc !== _milestoneLocationId;
	if (moved && scenePlateUrl(state, get(plateManifest))) {
		backgroundImage.set('');
		_milestoneLocationId = null;
	}
}

/** Whether Turn 0 init has completed (gates the three-pane view) */
export const isInitialized = writable<boolean>(false);

/** Epoch choice buttons (empty in Phase 4 / open mode) */
export const uiChoices = writable<string[]>([]);

/** Dream interlude text from Hypnos (displayed as full-screen overlay) */
export const activeDream = writable<string>('');

// ── The Tell: the flinch token ──────────────────────────────────
//
// A charged turn (Nemesis/Eris strike, doom advance, invalid action) emits a
// one-shot token; TheThread's committed block reads it once to play an entrance
// flinch that settles to pristine. Charged events surface at two times —
// nemesis/eris/invalid on the `mechanic` event, atropos/doom only at `state` —
// so detection runs in both, guarded to at most one flinch per committed turn.

/** A one-shot prose-flinch instruction. seq is monotonic; a consumer fires only
    on a strictly-newer seq, so a fresh mount can never replay a stale tell. */
export interface FlinchToken {
	agent: FlinchAgent;
	intensity: number;
	seq: number;
}

export const flinchToken = writable<FlinchToken>({ agent: 'none', intensity: 0, seq: 0 });

/** Session memory the pure IR refuses to hold: the prior committed doom stage
    (for the advance delta) and the once-per-turn emit guard. */
let _prevDoomStage: number | null = null;
let _flinchEmittedThisTurn = false;

/** Emit a flinch if the derivation finds a charged agent. At most one per turn:
    the `state` phase only fires if `mechanic` didn't already. */
function emitFlinch(state: ThreadState | null, event: MechanicEvent | null): void {
	if (_flinchEmittedThisTurn) return;
	const f = deriveFlinch(state, event, _prevDoomStage);
	if (f.agent === 'none') return;
	_flinchEmittedThisTurn = true;
	flinchToken.update((t) => ({ agent: f.agent, intensity: f.intensity, seq: t.seq + 1 }));
}

/** Dismiss the dream overlay — called by [ Awaken ] button */
export function dismissDream(): void {
	activeDream.set('');
}

// ── The Vigil: the crisis interstitial ──────────────────────────
//
// Holds the static care payload while it is shown. Set by the server's
// position-0 `crisis_resources` SSE frame (gate-on) OR by a CrisisLink click
// (the hardcoded client copy, always available). It is INDEPENDENT of game
// state: opening or dismissing it never touches gameState/isTerminal/proseHistory,
// so the fiction is never softened to be kind to the person (SAFE-C6/C9).

export const crisisInterstitial = writable<CrisisResources | null>(null);

/** Open the care surface with the given (static) resources. */
export function openCrisis(resources: CrisisResources): void {
	crisisInterstitial.set(resources);
}

/** Dismiss the care surface — only ever on an explicit player click. */
export function dismissCrisis(): void {
	crisisInterstitial.set(null);
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
		// The Vigil: carry self-asserted content prefs (not yet acted on).
		body: JSON.stringify({ ...params, content_prefs: currentContentPrefs() }),
	});

	if (!res.ok) throw new Error('Initialization failed');

	const result: TurnResult = await res.json();

	_sessionId = result.session_id;
	if (!_sessionId) {
		console.error('[nyx] CRITICAL: No session_id in /init response!', Object.keys(result));
	}
	saveResumeToken(result.resume_token);   // durability: persist the resume handle
	gameState.set(result.state);
	proseHistory.set([result.prose]);
	uiChoices.set(result.ui_choices || []);
	deliberationTrace.set(result.state.recent_traces?.at(-1) ?? null);
	repairWitness.set(null);
	isInitialized.set(true);

	// The Tell: a new incarnation never inherits the prior life's tell (VS-E13).
	flinchToken.set({ agent: 'none', intensity: 0, seq: 0 });
	_prevDoomStage = null;
	_flinchEmittedThisTurn = false;

	// The Ink: fetch this world's plates — fire-and-forget, self-catching
	// (INK-E5: never awaited in the init path, never throws into it).
	void loadPlates(result.state?.world_id);

	return result;
}

// ── Durability: resume a persisted thread on boot (sub-slice 4) ──────

/**
 * Attempt to rehydrate a living (or dead) thread from the stored resume token.
 *
 * Returns true if a thread was restored (the game view should show), false if
 * there is nothing to resume or it can no longer be restored (stay on title).
 * SC-6/UP-4: a terminal thread resumes straight into the Death Rite — permanence
 * is not undone by a refresh.
 */
export async function resumeGame(): Promise<boolean> {
	const token = getStoredResumeToken();
	if (!token) return false;

	let res: Response;
	try {
		res = await fetch('/api/resume', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ resume_token: token }),
		});
	} catch {
		return false; // network error — keep the token, retry next boot
	}

	if (res.status === 404) {
		clearResumeToken(); // unrestorable (unknown / stale schema) — start fresh
		return false;
	}
	// V2-MED: any other non-OK (500 corruption OR a transient hiccup/restart) —
	// KEEP the token and retry next boot. A rare truly-corrupt snapshot just
	// re-fails harmlessly (the player can start fresh from the vestibule);
	// clearing here would permanently orphan a life on a transient error.
	if (!res.ok) return false;

	const result: TurnResult = await res.json();
	if (!result.session_id) return false;

	// V2-MED (boot race): onMount awaits this resume while the vestibule is still
	// interactive. If the player started a NEW life during the in-flight request
	// (initGame set isInitialized), that life owns the stores now — yield rather
	// than stomp it back to the old thread. No await below this line, so the
	// check and the commit are one atomic synchronous block.
	if (get(isInitialized)) return false;

	_sessionId = result.session_id;
	saveResumeToken(result.resume_token);
	gameState.set(result.state);
	proseHistory.set(result.prose ? [result.prose] : []);
	uiChoices.set(result.ui_choices || []);
	deliberationTrace.set(result.state.recent_traces?.at(-1) ?? null);
	repairWitness.set(null);

	// SC-6/UP-4: rehydrate the death, don't swallow it.
	if (result.terminal) {
		isTerminal.set(true);
		deathReason.set(result.death_reason || '');
		epitaph.set(result.epitaph || '');
		bookId.set(result.book_id || '');
	}

	flinchToken.set({ agent: 'none', intensity: 0, seq: 0 });
	_prevDoomStage = null;
	_flinchEmittedThisTurn = false;
	void loadPlates(result.state?.world_id);
	isInitialized.set(true);
	return true;
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
	_flinchEmittedThisTurn = false; // re-arm: one flinch per committed turn

	let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
	try {
		const response = await fetch('/api/turn', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ action, session_id: _sessionId, content_prefs: currentContentPrefs() }),
		});

		// A transport-level fetch reject (offline, backend restart, CORS) throws
		// here, and a bad HTTP response throws just below — both now inside the
		// try, so the finally always clears isProcessing; the UI never sticks on
		// "The Fates deliberate..." after a network failure.
		if (!response.ok || !response.body) {
			throw new Error('Connection to the Nyx Engine lost.');
		}

		reader = response.body.getReader();
		const decoder = new TextDecoder('utf-8');
		let buffer = '';
		let fullProse = '';

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
		reader?.releaseLock();

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
 * Exported for unit testing the per-event-type store contracts (notably the
 * Vigil's SAFE-C9 invariant: a crisis_resources frame must not touch game state).
 */
export function handleStreamEvent(data: Record<string, unknown>): void {
	switch (data.type) {
		case 'mechanic': {
			const payload = data.payload as MechanicEvent;
			mechanicToast.set(payload);
			// Auto-clear toast after 2.5s
			setTimeout(() => mechanicToast.set(null), 2500);
			// The Tell: nemesis/eris/invalid surface here, before prose.
			emitFlinch(get(gameState), payload);
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

			// The Ink: the milestone yields when the scene it crowned ends.
			yieldMilestoneIfSceneChanged(payload);

			// The Tell: atropos/doom-advance are only knowable now. Suppress on
			// a terminal turn — the death sever owns the block (VS-E14). The
			// committed prose mounts after this, so the token is ready in time.
			if (!terminal) emitFlinch(payload, get(mechanicToast));
			_prevDoomStage = payload.doom?.active ? (payload.doom.stage ?? 0) : null;

			if (terminal) {
				isTerminal.set(true);
				deathReason.set(death);
				epitaph.set((data.epitaph as string) || '');
				bookId.set((data.book_id as string) || '');
			}

			// Player regains control on state event
			isProcessing.set(false);
			break;
		}

		case 'image': {
			const url = data.url as string;
			if (url) {
				backgroundImage.set(url);
				// The Ink: remember where the player stood when the milestone
				// arrived (the image fires post-stream, after the state event,
				// so gameState already holds this turn's scene).
				_milestoneLocationId =
					get(gameState)?.canon?.current_scene?.location_id ?? null;
			}
			break;
		}

		case 'dream': {
			const dreamText = data.text as string;
			if (dreamText) {
				activeDream.set(dreamText);
				// The Ink: a dream interlude is a scene boundary — the
				// milestone yields when a plate exists to resume to.
				if (get(backgroundImage) && scenePlateUrl(get(gameState), get(plateManifest))) {
					backgroundImage.set('');
					_milestoneLocationId = null;
				}
			}
			break;
		}

		case 'crisis_resources': {
			// The Vigil: the server yields this at stream position 0 on a flagged
			// turn (gate-on). Open the interstitial WITHOUT touching any game store
			// — the turn (incl. a self-destruction death) resolves untouched, and
			// the card stays up until the player explicitly dismisses it.
			const payload = data.payload as CrisisResources;
			if (payload) openCrisis(payload);
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
	clearResumeToken();   // the life is over — don't resume it on next boot
	gameState.set(null);
	proseHistory.set([]);
	streamingProse.set('');
	mechanicToast.set(null);
	deliberationTrace.set(null);
	repairWitness.set(null);
	backgroundImage.set('');
	_milestoneLocationId = null;
	clearPlates();
	flinchToken.set({ agent: 'none', intensity: 0, seq: 0 });
	_prevDoomStage = null;
	_flinchEmittedThisTurn = false;
	isProcessing.set(false);
	isTerminal.set(false);
	deathReason.set('');
	epitaph.set('');
	bookId.set('');
	uiChoices.set([]);
	activeDream.set('');
	isInitialized.set(false);
	vestibuleState.set('title');
}
