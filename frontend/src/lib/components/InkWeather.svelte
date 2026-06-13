<!--
  THE INK — ambient weather layer.
  One fixed stacking context (z-1, pointer-events: none); children layer by
  DOM order only — no per-child z-index (root-level layers break under the
  .game-grid fade-in stacking context). Reads deterministic state, paints
  deterministic weather: zero new truth, zero LLM calls.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import { gameState, mechanicToast } from '$lib/stores/engine';
	import { deriveViewSpec } from '$lib/viewspec/viewspec';

	// The room's steady state: the Ink, plus the dominant soul vector's grammar
	// and the lingering memory of the last intervention (The Tell, Phase B).
	let ambient = $derived(deriveViewSpec($gameState).ambient);

	/** One-shot strike ripple — keyed remount per Nemesis/Eris strike.
	    Increments only on the false→true toast edge (never on clear, never
	    on ordinary checks); untrack() keeps the write from re-triggering
	    the effect. */
	let strikeSeq = $state(0);
	let strikeKind = $state('');
	let prevStruck = false;
	$effect(() => {
		const toast = $mechanicToast;
		const struck = Boolean(toast && (toast.nemesis_struck || toast.eris_struck));
		if (struck && !prevStruck) {
			const kind = toast!.nemesis_struck ? 'nemesis' : 'eris';
			untrack(() => {
				strikeKind = kind;
				strikeSeq += 1;
			});
		}
		prevStruck = struck;
	});
</script>

<div
	class="ink-weather"
	data-soul={ambient.soulVector}
	class:nemesis-tint={ambient.lastIntervention === 'nemesis'}
	class:eris-tint={ambient.lastIntervention === 'eris'}
	aria-hidden="true"
	style="--ink-turbulence: {ambient.turbulence}; --ink-doom: {ambient.doom}; --ink-edge: {ambient.edge}; --ink-tint: {ambient.tint}; --ink-soul-bias: {ambient.soulBias};"
>
	<!-- the pool: edge vignette, deepens with wounds / faction heat -->
	<div class="ink-pool"></div>
	<!-- the drift: pale wisps that roil with omen -->
	<div class="ink-drift"></div>
	<!-- the bleed: doom presses in from the frame -->
	<div class="ink-doom-bleed"></div>
	<!-- the wash: epoch tint, center-masked -->
	<div class="ink-epoch-tint"></div>
	<!-- the strike: one-shot ripple when a Fate intervenes -->
	{#key strikeSeq}
		{#if strikeSeq > 0}
			<div class="ink-strike" class:eris={strikeKind === 'eris'}></div>
		{/if}
	{/key}
</div>
