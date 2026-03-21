<!--
  Right Pane (300px): The Oracle
  Displays current prophecy, turn counter, dominant vector, and milestone flash.
-->
<script lang="ts">
	import { deliberationTrace, gameState } from '$lib/stores/engine';

	let prophecy = $derived<string>(
		$gameState?.the_loom.current_prophecy ?? ''
	);

	let milestoneReached = $derived<boolean>(
		$gameState?.the_loom.milestone_reached ?? false
	);

	let trace = $derived.by(() => {
		const traces = $gameState?.recent_traces ?? [];
		return $deliberationTrace ?? (traces.length > 0 ? traces[traces.length - 1] : null);
	});

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

	{#if trace}
		<div class="mt-8 pt-6 border-t border-[var(--nyx-border)]/60">
			<details>
				<summary
					class="cursor-pointer text-[10px] uppercase tracking-[0.25em]"
					style="color: var(--nyx-text-dim);"
				>
					The Fates Deliberated
				</summary>

				<div class="mt-4 flex flex-col gap-4">
					{#if trace.winner_order.length > 0}
						<p
							class="text-[11px] uppercase tracking-[0.18em]"
							style="font-family: var(--font-mono); color: var(--nyx-oracle-gold);"
						>
							{trace.winner_order.join(' > ')}
						</p>
					{/if}

					{#if trace.final_reason}
						<p
							class="text-sm leading-relaxed"
							style="font-family: var(--font-prose); color: var(--nyx-text-dim);"
						>
							{trace.final_reason}
						</p>
					{/if}

					<div class="flex flex-col gap-3">
						{#each trace.proposals as proposal}
							<div class="border-l border-[var(--nyx-border)]/60 pl-3">
								<p
									class="text-[10px] uppercase tracking-[0.18em] mb-1"
									style="font-family: var(--font-mono); color: var(--nyx-text-dim);"
								>
									{proposal.agent}
								</p>
								<p
									class="text-sm leading-relaxed"
									style="font-family: var(--font-prose); color: var(--nyx-text);"
								>
									{proposal.intervention_copy || proposal.refusal_reason || proposal.priority_note}
								</p>
							</div>
						{/each}
					</div>
				</div>
			</details>
		</div>
	{/if}
</aside>
