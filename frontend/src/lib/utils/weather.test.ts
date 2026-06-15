import { describe, it, expect } from 'vitest';
import type { ThreadState } from '$lib/types/engine';
import {
	omenTurbulence,
	doomIntensity,
	edgeDarkening,
	epochTint,
	deriveWeather
} from './weather';

/** Build a loose partial state — these functions read only specific optional
 *  fields via optional chaining, so a minimal object is faithful. */
const st = (p: Record<string, unknown>) => p as unknown as ThreadState;

describe('omenTurbulence', () => {
	it('is 0 for a null state (INK-E1 totality)', () => {
		expect(omenTurbulence(null)).toBe(0);
	});
	it('scales omen/6 and saturates at 1', () => {
		expect(omenTurbulence(st({ pressures: { omen: 3 } }))).toBeCloseTo(0.5);
		expect(omenTurbulence(st({ pressures: { omen: 6 } }))).toBe(1);
		expect(omenTurbulence(st({ pressures: { omen: 99 } }))).toBe(1); // clamp (INK-E4)
	});
	it('collapses NaN to 0 (INK-E4)', () => {
		expect(omenTurbulence(st({ pressures: { omen: NaN } }))).toBe(0);
	});
});

describe('doomIntensity', () => {
	it('is 0 when doom is inactive or absent', () => {
		expect(doomIntensity(null)).toBe(0);
		expect(doomIntensity(st({ doom: { active: false, stage: 2, max_stage: 3 } }))).toBe(0);
	});
	it('is 0 when max_stage is non-positive (no divide-by-zero)', () => {
		expect(doomIntensity(st({ doom: { active: true, stage: 1, max_stage: 0 } }))).toBe(0);
	});
	it('is stage/max_stage, clamped', () => {
		expect(doomIntensity(st({ doom: { active: true, stage: 1, max_stage: 3 } }))).toBeCloseTo(1 / 3);
		expect(doomIntensity(st({ doom: { active: true, stage: 9, max_stage: 3 } }))).toBe(1);
	});
});

describe('edgeDarkening', () => {
	it('takes the max of wounds and faction heat over 10', () => {
		expect(edgeDarkening(st({ pressures: { wounds: 5, faction_heat: 2 } }))).toBeCloseTo(0.5);
		expect(edgeDarkening(st({ pressures: { wounds: 2, faction_heat: 10 } }))).toBe(1);
	});
	it('is 0 for a null state', () => {
		expect(edgeDarkening(null)).toBe(0);
	});
});

describe('epochTint', () => {
	it('returns a wash per epoch phase', () => {
		expect(epochTint(st({ session: { epoch_phase: 1 } }))).toContain('184, 134, 11');
		expect(epochTint(st({ session: { epoch_phase: 4 } }))).toContain('120, 40, 40');
	});
	it('falls back to phase-1 for null or unknown phase', () => {
		expect(epochTint(null)).toBe(epochTint(st({ session: { epoch_phase: 1 } })));
		expect(epochTint(st({ session: { epoch_phase: 99 } }))).toBe(
			epochTint(st({ session: { epoch_phase: 1 } }))
		);
	});
	it('every tint stays within the alpha budget (≤ 0.08)', () => {
		for (const phase of [1, 2, 3, 4]) {
			const alpha = Number(epochTint(st({ session: { epoch_phase: phase } })).match(/[\d.]+(?=\))/)![0]);
			expect(alpha).toBeLessThanOrEqual(0.08);
		}
	});
});

describe('deriveWeather', () => {
	it('null state yields the calm identity', () => {
		const w = deriveWeather(null);
		expect(w.turbulence).toBe(0);
		expect(w.doom).toBe(0);
		expect(w.edge).toBe(0);
		expect(typeof w.tint).toBe('string');
	});
	it('composes the four channels', () => {
		const w = deriveWeather(
			st({
				pressures: { omen: 6, wounds: 10 },
				doom: { active: true, stage: 3, max_stage: 3 },
				session: { epoch_phase: 2 }
			})
		);
		expect(w.turbulence).toBe(1);
		expect(w.doom).toBe(1);
		expect(w.edge).toBe(1);
		expect(w.tint).toContain('150, 150, 160');
	});
});
