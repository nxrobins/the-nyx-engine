import { describe, it, expect } from 'vitest';
import { CRISIS_FALLBACK } from './safety';

// The Vigil's always-on backstop (SAFE-C3/C8): the hardcoded, gate-independent,
// network-independent crisis copy the <CrisisLink/> renders on every screen. It
// is the honest fallback for everything the detector misses and for when the
// server is down or the gate is off — so its lifeline content must never be
// silently blanked. This mirrors the backend SAFE-C5 invariant on the server's
// CRISIS_RESOURCES (backend tests/test_welfare.py). We assert STRUCTURAL tokens,
// not the exact draft prose, so reviewer copy edits survive but a dropped
// lifeline fails RED.
describe('CRISIS_FALLBACK — the always-on lifeline must stay intact', () => {
	const flat = JSON.stringify(CRISIS_FALLBACK).toLowerCase();

	it('references the 988 US crisis line', () => {
		expect(flat).toContain('988');
	});

	it('includes the international findahelpline pointer (non-US players)', () => {
		expect(flat).toContain('findahelpline.com');
	});

	it('carries a non-empty disclaimer that it is a game, not a counseling service', () => {
		expect(CRISIS_FALLBACK.disclaimer.trim().length).toBeGreaterThan(0);
		expect(flat).toContain('not'); // "...does NOT counsel/monitor/follow up"
		expect(flat).toMatch(/game/);
	});

	it('offers at least one fully-formed resource (label + detail)', () => {
		expect(CRISIS_FALLBACK.resources.length).toBeGreaterThan(0);
		for (const r of CRISIS_FALLBACK.resources) {
			expect(r.label.trim().length).toBeGreaterThan(0);
			expect(r.detail.trim().length).toBeGreaterThan(0);
		}
	});

	it('is flagged draft (pending human/clinical review) and has a body', () => {
		expect(CRISIS_FALLBACK.draft).toBe(true);
		expect(CRISIS_FALLBACK.body.trim().length).toBeGreaterThan(0);
	});
});
