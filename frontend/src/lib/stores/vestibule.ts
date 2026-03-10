/**
 * Vestibule Store — Title Screen + Incarnation state.
 *
 * Manages: player UUID persistence, vestibule phase routing,
 * and past-thread fetching for the Title Screen ghost lines.
 */

import { writable } from 'svelte/store';
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
