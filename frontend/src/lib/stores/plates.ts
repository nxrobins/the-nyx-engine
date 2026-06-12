/**
 * The Plates — a world's curated canon images (The Ink, Layer 1).
 *
 * The manifest is fetched fire-and-forget after incarnation (INK-E5: never
 * awaited in the init critical path, never throws into it) and any failure
 * collapses to {} — the game renders exactly as it does without art.
 */

import { writable } from 'svelte/store';
import type { ThreadState } from '$lib/types/engine';

/** plate stem (settlement | home | faction | npc_<id>) → server-built URL */
export const plateManifest = writable<Record<string, string>>({});

/** Mirrors the backend's world_id law — an invalid id never leaves the client. */
const WORLD_ID_RE = /^[a-z0-9][a-z0-9-]{2,62}$/;

/** Monotonic request token — a stale response is discarded, never applied. */
let _loadSeq = 0;

/**
 * Load a world's plate manifest. Fire-and-forget; self-catching.
 * No-ops on a falsy or unlawful world_id (GET /plates/undefined is
 * unreachable by construction).
 */
export async function loadPlates(worldId: string | null | undefined): Promise<void> {
	if (!worldId || !WORLD_ID_RE.test(worldId)) return;
	const seq = ++_loadSeq;
	try {
		const res = await fetch(`/api/plates/${worldId}`);
		if (seq !== _loadSeq) return; // a newer load superseded this one
		if (!res.ok) {
			plateManifest.set({});
			return;
		}
		const data = await res.json();
		if (seq !== _loadSeq) return;
		plateManifest.set(data?.plates ?? {});
	} catch {
		if (seq === _loadSeq) plateManifest.set({});
	}
}

/** Forget the shelf (death / reset). Invalidates any in-flight load. */
export function clearPlates(): void {
	_loadSeq++;
	plateManifest.set({});
}

/**
 * The scene's plate: the home plate when the current location carries the
 * `home` tag, else the settlement plate, else ''. Null-safe everywhere
 * (INK-E1) — a null scene simply falls back to the settlement.
 */
export function scenePlateUrl(
	state: ThreadState | null,
	manifest: Record<string, string>
): string {
	const locId = state?.canon?.current_scene?.location_id;
	if (locId) {
		const loc = state?.canon?.locations?.[locId];
		if (loc?.tags?.includes('home') && manifest['home']) {
			return manifest['home'];
		}
	}
	return manifest['settlement'] ?? '';
}
