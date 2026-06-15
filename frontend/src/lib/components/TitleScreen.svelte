<!--
  TitleScreen.svelte — "The Tapestry"
  Hypnotic ambient void: ash particles, golden thread, past-life ghost lines.
  Click anywhere to proceed to Incarnation.
-->
<script lang="ts">
	import { get } from 'svelte/store';
	import {
		vestibuleState,
		pastThreads,
		fetchPastThreads,
		safetyReviewed,
		hasCurrentConsent
	} from '$lib/stores/vestibule';
	import { libraryBooks, fetchLibrary } from '$lib/stores/library';
	import Library from './Library.svelte';
	import type { PastThread } from '$lib/types/vestibule';

	let hoveredThread = $state<PastThread | null>(null);
	let libraryOpen = $state(false);

	// Fetch past threads + the shelf on mount
	$effect(() => {
		fetchPastThreads();
		fetchLibrary();
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
		if (libraryOpen) return; // the Library owns the screen while open
		// The Vigil: first-run consent gate, but ONLY when the care surface is
		// reviewed (gate-on). While off (the default), this is today's behavior.
		if (get(safetyReviewed) && !hasCurrentConsent()) {
			vestibuleState.set('consent');
		} else {
			vestibuleState.set('incarnation');
		}
	}

	function openLibrary(e: MouseEvent) {
		e.stopPropagation();
		libraryOpen = true;
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

	<!-- The Library entry (only when the shelf holds at least one life) -->
	{#if $libraryBooks.length > 0 && !libraryOpen}
		<button class="library-entry" onclick={openLibrary}>
			The Library of Severed Threads · {$libraryBooks.length}
		</button>
	{/if}

	<!-- The Library overlay -->
	{#if libraryOpen}
		<Library onClose={() => (libraryOpen = false)} />
	{/if}

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

	.library-entry {
		position: absolute;
		bottom: 2.5rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 20;
		background: transparent;
		border: none;
		cursor: pointer;
		font-family: var(--font-mono);
		font-size: 0.7rem;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--nyx-text-dim);
		transition: color 300ms ease;
	}

	.library-entry:hover {
		color: var(--nyx-oracle-gold);
	}
</style>
