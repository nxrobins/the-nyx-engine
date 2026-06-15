import { describe, it, expect } from 'vitest';
import type { ThreadState, MechanicEvent } from '$lib/types/engine';
import {
	dominantSoulVector,
	deriveFlinch,
	deriveAmbient,
	deriveViewSpec
} from './viewspec';

const st = (p: Record<string, unknown>) => p as unknown as ThreadState;
const ev = (p: Record<string, unknown>) => p as unknown as MechanicEvent;
const vectors = (metis: number, bia: number, kleos: number, aidos: number) =>
	st({ soul_ledger: { vectors: { metis, bia, kleos, aidos } } });

describe('dominantSoulVector (VS-E11 — no false dominance)', () => {
	it('returns neutral for a null state', () => {
		expect(dominantSoulVector(null)).toEqual({ vector: '', bias: 0 });
	});

	it('names the leader only when it clears the field by ≥ 1.0', () => {
		const { vector, bias } = dominantSoulVector(vectors(2, 8, 2, 2));
		expect(vector).toBe('bia');
		expect(bias).toBeGreaterThan(0);
		expect(bias).toBeLessThanOrEqual(1);
	});

	it('a near-tie (< 1.0 gap) resolves to neutral, not the array-first vector', () => {
		expect(dominantSoulVector(vectors(5, 5.5, 5, 5)).vector).toBe('');
	});

	it('the four-way Unformed opening is neutral', () => {
		expect(dominantSoulVector(vectors(5, 5, 5, 5)).vector).toBe('');
	});
});

describe('deriveFlinch (the one-shot charged-moment ladder)', () => {
	it('null/empty input yields no flinch', () => {
		const f = deriveFlinch(null, null, null);
		expect(f.agent).toBe('none');
		expect(f.intensity).toBe(0);
		expect(f.oneShot).toBe(true);
	});

	it('a Nemesis strike flinches as nemesis', () => {
		expect(deriveFlinch(st({}), ev({ nemesis_struck: true })).agent).toBe('nemesis');
	});

	it('an Eris strike flinches as eris', () => {
		expect(deriveFlinch(st({}), ev({ eris_struck: true })).agent).toBe('eris');
	});

	it('a doom stage advancing past prevDoomStage flinches as atropos', () => {
		const f = deriveFlinch(st({ doom: { active: true, stage: 2, max_stage: 3 } }), null, 1);
		expect(f.agent).toBe('atropos');
		expect(f.intensity).toBeGreaterThan(0);
	});

	it('an invalid action flinches as momus', () => {
		expect(deriveFlinch(st({}), ev({ valid: false })).agent).toBe('momus');
	});

	it('priority: a Nemesis strike outranks a co-occurring doom advance', () => {
		const f = deriveFlinch(
			st({ doom: { active: true, stage: 2, max_stage: 3 } }),
			ev({ nemesis_struck: true }),
			1
		);
		expect(f.agent).toBe('nemesis');
	});

	it('every flinch intensity stays clamped to [0,1]', () => {
		const f = deriveFlinch(
			st({ doom: { active: true, stage: 99, max_stage: 3 }, pressures: { omen: 99 } }),
			ev({ nemesis_struck: true })
		);
		expect(f.intensity).toBeGreaterThanOrEqual(0);
		expect(f.intensity).toBeLessThanOrEqual(1);
	});
});

describe('deriveAmbient / deriveViewSpec', () => {
	it('ambient carries the room’s last remembered intervention', () => {
		const a = deriveAmbient(st({ recent_traces: [{ winner_order: ['nemesis', 'clotho'] }] }));
		expect(a.lastIntervention).toBe('nemesis');
	});

	it('deriveViewSpec on null is the identity (calm ambient, no flinch)', () => {
		const spec = deriveViewSpec(null, null, null);
		expect(spec.flinch.agent).toBe('none');
		expect(spec.ambient.turbulence).toBe(0);
		expect(spec.ambient.soulVector).toBe('');
		expect(spec.ambient.lastIntervention).toBe('');
	});
});
