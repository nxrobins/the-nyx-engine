/**
 * Vestibule Store — Title Screen + Incarnation state.
 *
 * Manages: player UUID persistence, vestibule phase routing,
 * and past-thread fetching for the Title Screen ghost lines.
 */

import { get, writable } from 'svelte/store';
import type { VestibulePhase, PastThread } from '$lib/types/vestibule';

// ── Player ID (persistent UUID) ────────────────────────────────

function createPlayerId(): string {
	if (typeof localStorage !== 'undefined') {
		const stored = localStorage.getItem('nyx_player_id');
		if (stored) return stored;
	}

	// Generate new UUID
	const id =
		typeof crypto !== 'undefined' && crypto.randomUUID
			? crypto.randomUUID()
			: 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
					const r = (Math.random() * 16) | 0;
					const v = c === 'x' ? r : (r & 0x3) | 0x8;
					return v.toString(16);
				});

	if (typeof localStorage !== 'undefined') {
		localStorage.setItem('nyx_player_id', id);
	}

	return id;
}

export const playerId = writable<string>(createPlayerId());

// Persist changes (in case it's ever updated externally)
if (typeof localStorage !== 'undefined') {
	playerId.subscribe((id) => {
		localStorage.setItem('nyx_player_id', id);
	});
}

// ── Vestibule Phase ────────────────────────────────────────────

export const vestibuleState = writable<VestibulePhase>('title');

// ── Past Threads (Title Screen ghost lines) ────────────────────

export const pastThreads = writable<PastThread[]>([]);

/**
 * Fetch dead threads for the current player.
 * Silently fails — Title Screen renders fine with empty array.
 */
export async function fetchPastThreads(): Promise<void> {
	let id = '';
	playerId.subscribe((v) => (id = v))();

	try {
		const res = await fetch(`/api/threads/${encodeURIComponent(id)}`);
		if (!res.ok) return;
		const data = await res.json();
		pastThreads.set(data.threads || []);
	} catch {
		// Silent fail — no past lives is fine
	}
}

// ── The Vigil: safety gate + consent ───────────────────────────
//
// `safetyReviewed` is hydrated once from GET /safety. It gates ONLY the consent
// flow (and the server-enriched interstitial); the always-on CrisisLink never
// depends on it. While false (the shipped default) the flow is identical to
// today. If the flag is unreadable, it defaults false (withhold the gated
// surface) — the hardcoded client link still shows (SAFE-C3, the matrix).

export const CONSENT_VERSION = '1';

export interface ConsentRecord {
	version: string;
	age_affirmed: boolean;
	accepted_at: string;
}

function loadConsent(): ConsentRecord | null {
	if (typeof localStorage === 'undefined') return null;
	try {
		const raw = localStorage.getItem('nyx_consent');
		return raw ? (JSON.parse(raw) as ConsentRecord) : null;
	} catch {
		return null;
	}
}

export const consent = writable<ConsentRecord | null>(loadConsent());

/** True only when this device holds a current-version, affirmed consent. */
export function hasCurrentConsent(): boolean {
	const c = get(consent);
	return !!c && c.version === CONSENT_VERSION && c.age_affirmed === true;
}

/** Record the self-asserted acknowledgement (per-device, AG-C4). */
export function acceptConsent(): void {
	const rec: ConsentRecord = {
		version: CONSENT_VERSION,
		age_affirmed: true,
		accepted_at: new Date().toISOString()
	};
	consent.set(rec);
	if (typeof localStorage !== 'undefined') {
		try {
			localStorage.setItem('nyx_consent', JSON.stringify(rec));
		} catch {
			// non-fatal — consent simply won't persist across reloads on this device
		}
	}
}

/** The self-asserted content prefs carried on every request (never acted on yet). */
export function currentContentPrefs(): { age_affirmed: boolean; consent_version: string } {
	const c = get(consent);
	return { age_affirmed: !!c?.age_affirmed, consent_version: c?.version ?? '' };
}

export const safetyReviewed = writable<boolean>(false);

/** Hydrate the gate state from the server. Fail-closed: any error → false. */
export async function loadSafety(): Promise<void> {
	try {
		const res = await fetch('/api/safety');
		if (!res.ok) return; // unreadable → stays false (the client link still shows)
		const data = await res.json();
		safetyReviewed.set(!!data.reviewed);
	} catch {
		// Default false; the hardcoded CrisisLink remains the backstop.
	}
}
