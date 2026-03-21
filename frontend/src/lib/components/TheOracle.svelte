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

	let marks = $derived.by(() => {
		const next: { title: string; body: string; tone: string }[] = [];
		const pressures = $gameState?.pressures;
		const vectors = $gameState?.soul_ledger.vectors;
		const currentScene = $gameState?.canon?.current_scene;
		const winnerOrder = trace?.winner_order ?? [];
		const activeBrokenOath = ($gameState?.soul_ledger.active_oaths ?? []).some(
			(oath) => oath.status === 'broken'
		);

		if (winnerOrder[0] === 'lachesis' && currentScene?.immediate_problem) {
			next.push({
				title: 'Lachesis',
				body: currentScene.immediate_problem,
				tone: 'var(--nyx-text-dim)'
			});
		}

		if ((pressures?.omen ?? 0) >= 0.8) {
			next.push({
				title: 'Omen',
				body: `Fate presses close. Omen weight ${pressures?.omen.toFixed(1)} still hangs over the scene.`,
				tone: 'var(--nyx-oracle-gold)'
			});
		}

		if (winnerOrder.includes('nemesis') || $gameState?.last_outcome === 'nemesis') {
			next.push({
				title: 'Nemesis',
				body: trace?.proposals.find((proposal) => proposal.agent === 'nemesis')?.intervention_copy
					|| 'Judgment has marked the thread. The world will remember the offense.',
				tone: 'var(--nyx-nemesis)'
			});
		}

		if (winnerOrder.includes('eris') || $gameState?.last_outcome === 'eris') {
			next.push({
				title: 'Eris',
				body: trace?.proposals.find((proposal) => proposal.agent === 'eris')?.intervention_copy
					|| 'The weave has slipped. Disorder is now part of the scene.',
				tone: 'var(--nyx-text)'
			});
		}

		if (vectors) {
			const floor = Math.min(vectors.metis, vectors.bia, vectors.kleos, vectors.aidos);
			if (floor <= 2.5 || activeBrokenOath || (pressures?.wounds ?? 0) >= 2.5) {
				next.push({
					title: 'Atropos',
					body: activeBrokenOath
						? 'A broken oath has drawn the shears near.'
						: 'The thread thins. Finality is watching for the next failure.',
					tone: 'var(--nyx-text-dim)'
				});
			}
		}

		return next.slice(0, 4);
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

	{#if marks.length > 0}
		<div class="flex flex-col gap-3">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				Marks Upon The Thread
			</p>

			{#each marks as mark}
				<div class="border-l border-[var(--nyx-border)]/60 pl-3">
					<p
						class="text-[10px] uppercase tracking-[0.18em] mb-1"
						style="font-family: var(--font-mono); color: {mark.tone};"
					>
						{mark.title}
					</p>
					<p
						class="text-sm leading-relaxed"
						style="font-family: var(--font-prose); color: var(--nyx-text-dim);"
					>
						{mark.body}
					</p>
				</div>
			{/each}
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
