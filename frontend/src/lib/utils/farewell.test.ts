import { describe, it, expect } from 'vitest';
import type { ThreadState, CanonNPC } from '$lib/types/engine';
import { deriveFarewell } from './farewell';

const npc = (p: Partial<CanonNPC> & { npc_id: string; name: string }): CanonNPC =>
	({ role: 'friend', status: 'alive', trust: 0, fear: 0, obligation: 0, tags: [],
	   last_seen_turn: 1, home_location_id: 'h', current_location_id: 'h', ...p }) as CanonNPC;

const st = (...npcs: CanonNPC[]): ThreadState =>
	({ canon: { npcs: Object.fromEntries(npcs.map((n) => [n.npc_id, n])) } }) as unknown as ThreadState;

describe('deriveFarewell', () => {
	it('is empty and never throws on null / canon-less state', () => {
		expect(deriveFarewell(null)).toEqual({ lost: [], remaining: [] });
		expect(deriveFarewell({} as ThreadState)).toEqual({ lost: [], remaining: [] });
		expect(deriveFarewell({ canon: null } as unknown as ThreadState)).toEqual({ lost: [], remaining: [] });
	});

	it('separates the lost from those who remain, by status', () => {
		const f = deriveFarewell(st(
			npc({ npc_id: 'a', name: 'Sera', status: 'alive' }),
			npc({ npc_id: 'b', name: 'Kael', status: 'dead' }),
			npc({ npc_id: 'c', name: 'Mara', status: 'departed' }),
			npc({ npc_id: 'd', name: 'Ren', status: 'missing' })
		));
		expect(f.remaining.map((s) => s.name)).toEqual(['Sera']);
		expect(f.lost.map((d) => d.name).sort()).toEqual(['Kael', 'Mara', 'Ren']);
	});

	it('frames each loss from the deathbed', () => {
		const f = deriveFarewell(st(
			npc({ npc_id: 'a', name: 'A', status: 'dead' }),
			npc({ npc_id: 'b', name: 'B', status: 'departed' }),
			npc({ npc_id: 'c', name: 'C', status: 'missing' })
		));
		const fate = Object.fromEntries(f.lost.map((d) => [d.name, d.fate]));
		expect(fate.A).toBe('taken before you');
		expect(fate.B).toBe('gone from your life');
		expect(fate.C).toBe('never found');
	});

	it('carries roles for both groups', () => {
		const f = deriveFarewell(st(
			npc({ npc_id: 'a', name: 'Sera', role: 'mother', status: 'alive' }),
			npc({ npc_id: 'b', name: 'Kael', role: 'father', status: 'dead' })
		));
		expect(f.remaining[0]).toEqual({ name: 'Sera', role: 'mother' });
		expect(f.lost[0].role).toBe('father');
	});

	it('a life that ends alone leaves empty groups (a poignant nothing, not a crash)', () => {
		expect(deriveFarewell(st())).toEqual({ lost: [], remaining: [] });
	});
});
