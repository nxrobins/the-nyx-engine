/**
 * THE WITNESSES — the cast of a life, made legible.
 *
 * Pure derivation from ThreadState to a display model of the people in the
 * player's life: the living (with the trajectory of their bond and their standing
 * want) and the lost (taken by the world, departed in betrayal, or gone missing —
 * remembered, never erased). This surfaces the relationship-depth subsystem
 * (Sprint D's memory, the witnesses who leave, the world that takes them) which
 * until now lived only in prose.
 *
 * Total over every reachable state: a null/canon-less state yields empty lists,
 * never a throw. No DOM, no stores — unit-testable.
 */

import type { ThreadState, CanonNPC } from '$lib/types/engine';

export interface WitnessView {
	id: string;
	name: string;
	role: string;
	/** diegetic bond band for the living; '' for the lost */
	bondLabel: string;
	/** authored standing desire, for the living; '' for the lost */
	want: string;
	/** how they were lost, for the dead/departed/missing; '' for the living */
	fate: string;
}

export interface Witnesses {
	living: WitnessView[];
	lost: WitnessView[];
}

const LOST_FATE: Record<string, string> = {
	dead: 'taken by the world',
	departed: 'left your life',
	missing: 'lost to you'
};

/** Mirror of canon's bond bands, in the player's voice. Betrayal past returning
 *  dominates — a soured bond reads as estrangement no matter the raw number. */
function bondLabel(bond: number, betrayalCount: number): string {
	if (betrayalCount >= 4) return 'will not forgive you';
	if (bond >= 6) return 'bound to you';
	if (bond >= 2) return 'warm to you';
	if (bond > -2) return 'wary of you';
	if (bond > -6) return 'estranged';
	return 'will not forgive you';
}

export function deriveWitnesses(state: ThreadState | null): Witnesses {
	const npcs = state?.canon?.npcs;
	if (!npcs) return { living: [], lost: [] };

	const living: (WitnessView & { _bond: number })[] = [];
	const lost: WitnessView[] = [];

	for (const npc of Object.values(npcs) as CanonNPC[]) {
		if (npc.status === 'alive') {
			living.push({
				id: npc.npc_id,
				name: npc.name,
				role: npc.role,
				bondLabel: bondLabel(npc.bond ?? 0, npc.betrayal_count ?? 0),
				want: npc.want ?? '',
				fate: '',
				_bond: npc.bond ?? 0
			});
		} else {
			lost.push({
				id: npc.npc_id,
				name: npc.name,
				role: npc.role,
				bondLabel: '',
				want: '',
				fate: LOST_FATE[npc.status] ?? 'gone'
			});
		}
	}

	// The living, closest bond first (stable sort preserves met-order on ties); the
	// lost stay in the order the life lost them.
	living.sort((a, b) => b._bond - a._bond);
	return { living: living.map(({ _bond, ...w }) => w), lost };
}
