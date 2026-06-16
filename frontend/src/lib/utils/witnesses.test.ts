import { describe, it, expect } from 'vitest';
import type { ThreadState, CanonNPC } from '$lib/types/engine';
import { deriveWitnesses } from './witnesses';

const npc = (p: Partial<CanonNPC> & { npc_id: string; name: string }): CanonNPC =>
	({ role: 'friend', status: 'alive', trust: 0, fear: 0, obligation: 0, tags: [],
	   last_seen_turn: 1, home_location_id: 'h', current_location_id: 'h', ...p }) as CanonNPC;

const st = (...npcs: CanonNPC[]): ThreadState =>
	({ canon: { npcs: Object.fromEntries(npcs.map((n) => [n.npc_id, n])) } }) as unknown as ThreadState;

describe('deriveWitnesses', () => {
	it('is empty and never throws on a null / canon-less state', () => {
		expect(deriveWitnesses(null)).toEqual({ living: [], lost: [] });
		expect(deriveWitnesses({} as ThreadState)).toEqual({ living: [], lost: [] });
		expect(deriveWitnesses({ canon: null } as unknown as ThreadState)).toEqual({ living: [], lost: [] });
	});

	it('partitions the living from the lost by status', () => {
		const w = deriveWitnesses(st(
			npc({ npc_id: 'npc_sera', name: 'Sera', status: 'alive' }),
			npc({ npc_id: 'npc_kael', name: 'Kael', status: 'dead' }),
			npc({ npc_id: 'npc_mara', name: 'Mara', status: 'departed' }),
			npc({ npc_id: 'npc_ren', name: 'Ren', status: 'missing' })
		));
		expect(w.living.map((x) => x.name)).toEqual(['Sera']);
		expect(w.lost.map((x) => x.name).sort()).toEqual(['Kael', 'Mara', 'Ren']);
	});

	it('maps each lost status to its fate phrase', () => {
		const w = deriveWitnesses(st(
			npc({ npc_id: 'a', name: 'A', status: 'dead' }),
			npc({ npc_id: 'b', name: 'B', status: 'departed' }),
			npc({ npc_id: 'c', name: 'C', status: 'missing' })
		));
		const fate = Object.fromEntries(w.lost.map((x) => [x.name, x.fate]));
		expect(fate.A).toBe('taken by the world');
		expect(fate.B).toBe('left your life');
		expect(fate.C).toBe('lost to you');
	});

	it('orders the living by bond strength, closest first', () => {
		const w = deriveWitnesses(st(
			npc({ npc_id: 'a', name: 'Distant', bond: -3 }),
			npc({ npc_id: 'b', name: 'Close', bond: 7 }),
			npc({ npc_id: 'c', name: 'Mild', bond: 1 })
		));
		expect(w.living.map((x) => x.name)).toEqual(['Close', 'Mild', 'Distant']);
	});

	it('labels the bond band, with betrayal past returning overriding', () => {
		const w = deriveWitnesses(st(
			npc({ npc_id: 'a', name: 'Bound', bond: 8 }),
			npc({ npc_id: 'b', name: 'Warm', bond: 3 }),
			npc({ npc_id: 'c', name: 'Wary', bond: 0 }),
			npc({ npc_id: 'd', name: 'Estranged', bond: -4 }),
			npc({ npc_id: 'e', name: 'Betrayed', bond: 9, betrayal_count: 4 })
		));
		const band = Object.fromEntries(w.living.map((x) => [x.name, x.bondLabel]));
		expect(band.Bound).toBe('bound to you');
		expect(band.Warm).toBe('warm to you');
		expect(band.Wary).toBe('wary of you');
		expect(band.Estranged).toBe('estranged');
		expect(band.Betrayed).toBe('will not forgive you'); // betrayal dominates the raw +9
	});

	it('carries the living NPC’s want and tolerates missing depth fields', () => {
		const w = deriveWitnesses(st(
			npc({ npc_id: 'a', name: 'Sera', want: 'to keep the household whole' }),
			npc({ npc_id: 'b', name: 'NoDepth' }) // no want/bond/betrayal_count
		));
		const sera = w.living.find((x) => x.name === 'Sera')!;
		expect(sera.want).toBe('to keep the household whole');
		const bare = w.living.find((x) => x.name === 'NoDepth')!;
		expect(bare.want).toBe('');
		expect(bare.bondLabel).toBe('wary of you'); // bond defaults to 0
	});
});
