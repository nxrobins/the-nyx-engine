/**
 * THE FAREWELL — the cast at the end of a life, for the Death Rite.
 *
 * Pure derivation from the final ThreadState into who the player LOST before the
 * end (the dead, the departed, the missing) and who REMAINS to outlive them. The
 * emotional payoff of the relationship subsystem: a life is measured by the people
 * in it, and death names them one last time.
 *
 * Total over every reachable state (null / canon-less → empty, never throws).
 * No DOM, no stores — unit-testable. Distinct from deriveWitnesses: framed from
 * the deathbed (who you leave behind), not the living scene.
 */

import type { ThreadState, CanonNPC } from '$lib/types/engine';

export interface Departed {
	name: string;
	role: string;
	/** how they were lost, from the dying player's vantage */
	fate: string;
}

export interface Survivor {
	name: string;
	role: string;
}

export interface Farewell {
	lost: Departed[];
	remaining: Survivor[];
}

const FATE: Record<string, string> = {
	dead: 'taken before you',
	departed: 'gone from your life',
	missing: 'never found'
};

export function deriveFarewell(state: ThreadState | null): Farewell {
	const npcs = state?.canon?.npcs;
	if (!npcs) return { lost: [], remaining: [] };

	const lost: Departed[] = [];
	const remaining: Survivor[] = [];
	for (const npc of Object.values(npcs) as CanonNPC[]) {
		if (npc.status === 'alive') {
			remaining.push({ name: npc.name, role: npc.role });
		} else {
			lost.push({ name: npc.name, role: npc.role, fate: FATE[npc.status] ?? 'gone' });
		}
	}
	return { lost, remaining };
}
