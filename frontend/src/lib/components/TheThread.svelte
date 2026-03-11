<!--
  Center Pane: The Thread — v3.0
  Paragraph pagination system with vertically centered anchor.
  Displays one paragraph at a time with ▼ advance button.
  Console only appears after the final paragraph.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import {
		proseHistory,
		hypnosStream,
		streamingProse,
		backgroundImage,
		isProcessing,
		isTerminal,
		uiChoices,
		gameState,
		submitAction,
	} from '$lib/stores/engine';
	import { renderProse } from '$lib/utils/markdown';
	import Console from './Console.svelte';

	/** Current paragraph index within the latest turn's prose */
	let visibleIndex = $state(0);

	/** Split the LATEST prose entry into paragraphs on \n\n */
	let paragraphs = $derived(
		$proseHistory.length > 0
			? $proseHistory[$proseHistory.length - 1]
					.split('\n\n')
					.filter((p: string) => p.trim() !== '')
			: []
	);

	/** Reset index when a new turn starts (isProcessing goes true) */
	let prevProcessing = false;
	$effect(() => {
		if ($isProcessing && !prevProcessing) {
			visibleIndex = 0;
		}
		prevProcessing = $isProcessing;
	});

	function advanceText() {
		if (visibleIndex < paragraphs.length - 1) {
			visibleIndex++;
		}
	}
</script>

<main class="relative flex flex-col h-full overflow-hidden">
	<!-- BFL Background Image -->
	{#if $backgroundImage}
		<div
			class="bfl-background visible"
			style="background-image: url('{$backgroundImage}');"
		></div>
	{/if}

	<!-- Scroll Area -->
	<div class="flex-1 overflow-y-auto relative z-10">
		<div class="thread-anchor-wrapper px-8 py-6">
			<!-- Top spacer (pushes content to vertical center) -->
			<div class="thread-anchor-spacer"></div>

			<!-- Welcome state (before any prose or streaming) -->
			{#if $proseHistory.length === 0 && !$hypnosStream}
				<div class="flex items-center justify-center">
					<p
						class="text-center italic"
						style="font-family: var(--font-prose); color: var(--nyx-text-dim); font-size: 1.125rem;"
					>
						Your thread begins to unwind...
					</p>
				</div>
			{/if}

			<!-- Diegetic loading state (processing, before any streaming arrives) -->
			{#if $isProcessing && !$hypnosStream && !$streamingProse}
				<div class="flex flex-col items-center justify-center fade-in">
					<div class="weaving-thread"></div>
					<p class="weaving-text">The Fates are weaving...</p>
				</div>
			{/if}

			<!-- Streaming prose (typewriter effect during Clotho Phase 2) -->
			{#if $isProcessing && $streamingProse}
				<div class="prose-nyx mb-6 max-w-2xl mx-auto clotho-enter">
					{@html renderProse($streamingProse)}
				</div>
			{/if}

			<!-- Hypnos filler stream (legacy fallback) -->
			{#if $hypnosStream}
				<div class="hypnos-text prose-nyx mb-6 max-w-2xl mx-auto">
					{@html renderProse($hypnosStream)}
				</div>
			{/if}

			<!-- Paginated paragraph display (after prose arrives) -->
			{#if paragraphs.length > 0 && !$hypnosStream && !$isProcessing}
				{#key visibleIndex}
					<div
						class="prose-nyx mb-6 max-w-2xl mx-auto"
						in:fade={{ duration: 600, delay: 200 }}
						out:fade={{ duration: 400 }}
					>
						{@html renderProse(paragraphs[visibleIndex] ?? '')}
					</div>
				{/key}
			{/if}

			<!-- Controls container (auto height for choice buttons) -->
			<div class="mt-8 flex flex-col gap-4 items-center justify-center">
				{#if $isTerminal}
					<!-- Terminal state always shows, bypasses pagination -->
					<Console />
				{:else if paragraphs.length > 0 && visibleIndex < paragraphs.length - 1 && !$hypnosStream && !$isProcessing}
					<!-- More paragraphs to read — show advance button -->
					<button
						onclick={advanceText}
						class="animate-pulse text-[var(--nyx-text-dim)] hover:text-[var(--nyx-text)] transition-colors text-lg"
						style="font-family: var(--font-prose);"
					>
						▼
					</button>
				{:else if !$isProcessing && $gameState}
					<!-- Final paragraph reached — show epoch controls -->
					{#if $gameState.session.ui_mode === 'buttons' && $uiChoices.length > 0}
						<div class="flex gap-4 flex-wrap justify-center fade-in">
							{#each $uiChoices as choice}
								<button
									class="nyx-choice-btn phase-{$gameState.session.epoch_phase}"
									onclick={() => submitAction(choice)}
								>
									{choice}
								</button>
							{/each}
						</div>
					{:else}
						<Console />
					{/if}
				{:else if !$isProcessing}
					<!-- No game state yet — show Console -->
					<Console />
				{/if}
			</div>

			<!-- Bottom spacer (pushes content to vertical center) -->
			<div class="thread-anchor-spacer"></div>
		</div>
	</div>
</main>
