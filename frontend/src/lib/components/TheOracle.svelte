<!--
  Right Pane (300px): The Oracle
  Displays current prophecy, turn counter, dominant vector, and milestone flash.
-->
<script lang="ts">
	import { gameState } from '$lib/stores/engine';

	let prophecy = $derived<string>(
		$gameState?.the_loom.current_prophecy ?? ''
	);

	let milestoneReached = $derived<boolean>(
		$gameState?.the_loom.milestone_reached ?? false
	);

	/** Track prophecy changes for flash animation */
	let prophecyAnimClass = $state('prophecy-pulse');
	let lastProphecy = '';

	$effect(() => {
		if (prophecy && prophecy !== lastProphecy && lastProphecy !== '') {
			prophecyAnimClass = 'prophecy-update';
			setTimeout(() => { prophecyAnimClass = 'prophecy-pulse'; }, 1200);
		}
		lastProphecy = prophecy;
	});
</script>

<aside
	class="h-full overflow-y-auto border-l border-[var(--nyx-border)] px-5 py-6 flex flex-col bg-[var(--nyx-void)]
		{milestoneReached ? 'milestone-flash' : ''}"
>
	<!-- Prophecy -->
	{#if prophecy}
		<div class="flex-1 flex flex-col justify-center">
			<p class="text-[10px] uppercase tracking-[0.25em] mb-4 text-right" style="color: var(--nyx-text-dim);">
				The Oracle Speaks
			</p>

			<blockquote
				class="text-right leading-relaxed {prophecyAnimClass}"
				style="
					font-family: var(--font-prose);
					font-style: italic;
					font-size: 1.05rem;
					color: var(--nyx-oracle-gold);
					opacity: 0.6;
				"
			>
				"{prophecy}"
			</blockquote>
		</div>
	{/if}
</aside>
