/**
 * The Vigil — the hardcoded, gate-independent, network-independent crisis copy
 * (SAFE-C3). This constant is the honest always-on backstop: the `<CrisisLink/>`
 * renders it with NO `GET /safety` call, NO `reviewed` flag, and NO network — so
 * a distressed person always has a real affordance even if the server is down,
 * the gate is off, or the SSE frame never arrives (AG-C3, AG-C5).
 *
 * It mirrors the server-owned `CRISIS_RESOURCES` (backend/app/services/welfare.py).
 * Both are DRAFT — pending human (ideally clinical) review. No copy here claims
 * the detector is complete; this link IS the declared backstop for what it misses.
 */

import type { CrisisResources } from '$lib/types/engine';

export const CRISIS_FALLBACK: CrisisResources = {
	title: "You don't have to face this alone",
	body:
		"If you're thinking about harming yourself or ending your life, please " +
		'reach out — you deserve to talk to someone trained to help, right now.',
	resources: [
		{
			label: '988 Suicide & Crisis Lifeline (US)',
			detail: 'Call or text 988, any time, day or night — or chat at 988lifeline.org.'
		},
		{
			label: 'Find a helpline anywhere',
			detail: 'findahelpline.com lists free, confidential support lines by country.'
		}
	],
	disclaimer:
		'This is a game. These are real, independent services — the game does not ' +
		'counsel you, monitor you, or follow up. Please reach out to them directly.',
	draft: true
};
