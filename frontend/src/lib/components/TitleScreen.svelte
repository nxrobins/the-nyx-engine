<!--
  TitleScreen.svelte — "The Tapestry"
  Hypnotic ambient void: ash particles, golden thread, past-life ghost lines.
  Click anywhere to proceed to Incarnation.
-->
<script lang="ts">
	import { vestibuleState, pastThreads, fetchPastThreads } from '$lib/stores/vestibule';
	import type { PastThread } from '$lib/types/vestibule';

	let hoveredThread = $state<PastThread | null>(null);

	// Fetch past threads on mount
	$effect(() => {
		fetchPastThreads();
	});

	// Generate ash particle properties (deterministic per index)
	function ashProps(i: number) {
		const delay = (i * 0.7) % 20;
		const duration = 10 + (i * 1.3) % 10;
		const left = (i * 3.7) % 100;
		const drift = -30 + (i * 7.1) % 60;
		return { delay, duration, left, drift };
	}

	// Past thread line positions — scattered in left/right thirds
	function threadLineLeft(i: number, total: number): number {
		// Alternate between left third (5-30%) and right third (70-95%)
		if (i % 2 === 0) {
			return 5 + ((i / 2) * 25) / Math.max(total / 2, 1);
		} else {
			return 70 + (((i - 1) / 2) * 25) / Math.max(total / 2, 1);
		}
	}

	function handleClick() {
		vestibuleState.set('incarnation');
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="title-screen" onclick={handleClick}>
	<!-- Ash particles -->
	{#each Array(30) as _, i}
		{@const props = ashProps(i)}
		<div
			class="ash-particle"
			style:--delay="{props.delay}s"
			style:--duration="{props.duration}s"
			style:--drift="{props.drift}px"
			style:left="{props.left}%"
		></div>
	{/each}

	<!-- Golden thread (center) -->
	<div class="golden-thread"></div>

	<!-- Past-life ghost threads -->
	{#each $pastThreads.slice(0, 10) as thread, i}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="past-thread-line"
			style:left="{threadLineLeft(i, Math.min($pastThreads.length, 10))}%"
			onmouseenter={() => (hoveredThread = thread)}
			onmouseleave={() => (hoveredThread = null)}
		></div>
	{/each}

	<!-- Title area (fades out when hovering a past thread) -->
	<div
		class="title-content"
		style:opacity={hoveredThread ? 0 : 1}
		style:transition="opacity 400ms ease"
	>
		<h1 class="loom-title">THE LOOM</h1>
		<p class="loom-subtitle hypnos-breathe">Click to awaken.</p>
	</div>

	<!-- Epitaph overlay (when hovering a past thread) -->
	{#if hoveredThread}
		<div class="epitaph-overlay fade-in">
			{#if hoveredThread.epitaph}
				<p class="epitaph-text">"{hoveredThread.epitaph}"</p>
			{:else}
				<p class="epitaph-text">"A thread lost to silence."</p>
			{/if}
			<p class="epitaph-meta">
				Flaw: {hoveredThread.hamartia} · Fell at turn {hoveredThread.final_turn}
			</p>
			{#if hoveredThread.legacy_mark}
				<p class="epitaph-meta" style="margin-top: 0.6rem;">
					Mark: {hoveredThread.legacy_mark}
				</p>
			{/if}
			{#if hoveredThread.legacy_effect}
				<p class="epitaph-meta" style="max-width: 32rem; text-align: center; letter-spacing: 0.04em; margin-top: 0.35rem;">
					{hoveredThread.legacy_effect}
				</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.title-content {
		position: relative;
		z-index: 10;
		text-align: center;
		pointer-events: none;
	}

	.loom-title {
		font-family: var(--font-prose);
		font-weight: 600;
		font-size: 3rem;
		color: var(--nyx-text);
		text-transform: uppercase;
		animation: loom-contract 6s ease-out forwards;
		margin: 0 0 1.5rem 0;
	}

	.loom-subtitle {
		font-family: var(--font-prose);
		font-style: italic;
		font-size: 1rem;
		color: var(--nyx-text-dim);
		margin: 0;
	}

	.epitaph-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		z-index: 10;
		pointer-events: none;
	}

	.epitaph-text {
		font-family: var(--font-prose);
		font-style: italic;
		font-size: 1.25rem;
		color: var(--nyx-oracle-gold);
		max-width: 500px;
		text-align: center;
		line-height: 1.8;
		margin: 0 0 0.75rem 0;
	}

	.epitaph-meta {
		font-family: var(--font-mono);
		font-size: 0.7rem;
		color: var(--nyx-text-dim);
		letter-spacing: 0.1em;
		margin: 0;
	}

	.hypnos-breathe {
		animation: hypnos-breathe 3s ease-in-out infinite;
	}
</style>
