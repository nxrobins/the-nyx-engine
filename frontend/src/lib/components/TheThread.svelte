<!--
  Center Pane: The Thread — v3.0
  Paragraph pagination system with vertically centered anchor.
  Displays one paragraph at a time with ▼ advance button.
  Console only appears after the final paragraph.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import { get } from 'svelte/store';
	import {
		proseHistory,
		streamingProse,
		backgroundImage,
		isProcessing,
		isTerminal,
		uiChoices,
		gameState,
		submitAction,
		activeDream,
		dismissDream,
		deliberationTrace,
		repairWitness,
		flinchToken,
	} from '$lib/stores/engine';
	import { renderProse } from '$lib/utils/markdown';
	import { plateManifest, scenePlateUrl } from '$lib/stores/plates';
	import Console from './Console.svelte';
	import DeathRite from './DeathRite.svelte';
	import Marginalia from './Marginalia.svelte';

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

	let trace = $derived.by(
		() => $deliberationTrace ?? $gameState?.recent_traces?.at(-1) ?? null
	);

	let witnessProposals = $derived.by(() => {
		if (!trace) return [];
		return trace.proposals
			.filter((proposal) =>
				trace.winner_order.includes(proposal.agent)
				|| Boolean(proposal.intervention_copy)
				|| Boolean(proposal.refusal_reason)
			)
			.slice(0, 3);
	});

	function advanceText() {
		if (visibleIndex < paragraphs.length - 1) {
			visibleIndex++;
		}
	}

	/** The Ink: milestone image wins while present; otherwise the scene's
	    plate; '' (today's bare ground) when the world has no art (INK-E6). */
	let bgUrl = $derived($backgroundImage || scenePlateUrl($gameState, $plateManifest));

	/** The Tell: the committed prose flinches once at a charged threshold, then
	    settles. `lastFlinchSeq` starts at the LIVE token seq (VS-E13) — a fresh
	    mount can never replay a stale tell, only a strictly-newer bump. The
	    flinch arms only on the first paragraph, off-terminal (sever owns death,
	    VS-E14), and disarms on animationend. */
	let lastFlinchSeq = $state(get(flinchToken).seq);
	let activeFlinch = $derived.by(() => {
		const t = $flinchToken;
		if ($isTerminal || $isProcessing) return null;
		if (t.seq === 0 || t.seq === lastFlinchSeq || visibleIndex !== 0) return null;
		return t;
	});
	function consumeFlinch() {
		lastFlinchSeq = $flinchToken.seq;
	}

	/** While Clotho streams, surface only the FIRST paragraph — the rest
	    arrives behind the curtain. The paginated read then opens on the
	    same paragraph the player was just watching form: no full-text
	    flash, no snap back. */
	let streamingFirst = $derived.by(() => {
		const text = $streamingProse.replace(/^\s+/, '');
		const cut = text.indexOf('\n\n');
		return cut === -1 ? text : text.slice(0, cut);
	});

	/** More paragraphs already woven beyond the visible one. */
	let streamingHasMore = $derived(
		$streamingProse.replace(/^\s+/, '').includes('\n\n')
	);
</script>

<main class="relative flex flex-col h-full overflow-hidden">
	<!-- The ground: milestone image or the world's scene plate (INK-E6 —
	     the guard is bgUrl, never $backgroundImage alone) -->
	{#if bgUrl}
		<div
			class="bfl-background visible"
			style="background-image: url('{bgUrl}');"
		></div>
	{/if}

	<!-- Marginalia: present-NPC portraits (decorative, ≥1100px) -->
	<Marginalia />

	<!-- Scroll Area -->
	<div class="flex-1 overflow-y-auto relative z-10">
		<div class="thread-anchor-wrapper px-8 py-6">
			<!-- Top spacer (pushes content to vertical center) -->
			<div class="thread-anchor-spacer"></div>

			<!-- Welcome state (before any prose or streaming) -->
			{#if $proseHistory.length === 0}
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
			{#if $isProcessing && !$streamingProse}
				<div class="flex flex-col items-center justify-center fade-in">
					<div class="weaving-thread"></div>
					<p class="weaving-text">The Fates are weaving...</p>
				</div>
			{/if}

			<!-- Streaming prose (typewriter effect during Clotho Phase 2).
			     Only the FIRST paragraph types in view; the rest of the
			     turn arrives unseen so the paginated read never snaps. -->
			{#if $isProcessing && $streamingProse}
				<div class="prose-nyx mb-6 max-w-2xl mx-auto clotho-enter">
					{@html renderProse(streamingFirst)}
				</div>
				{#if streamingHasMore}
					<div class="flex justify-center mb-6">
						<div class="weaving-thread weaving-thread-inline" title="The Fates still weave"></div>
					</div>
				{/if}
			{/if}

			<!-- Paginated paragraph display (after prose arrives).
			     QoL: the prose itself advances on click — the ▼ remains as
			     the affordance, the whole breath is the target. -->
			{#if paragraphs.length > 0 && !$isProcessing}
				{#key visibleIndex}
					<!-- The Tell: the flinch animates THIS wrapper (transform/
					     opacity/filter), never the resting .prose-nyx box —
					     geometry and the click target stay fixed (VS-E10). -->
					<div
						class="prose-flinch-wrap mb-6 max-w-2xl mx-auto"
						class:vs-flinch={activeFlinch}
						class:vs-nemesis={activeFlinch?.agent === 'nemesis'}
						class:vs-eris={activeFlinch?.agent === 'eris'}
						class:vs-atropos={activeFlinch?.agent === 'atropos'}
						class:vs-momus={activeFlinch?.agent === 'momus'}
						class:vs-sever={$isTerminal}
						style="--vs-flinch-intensity: {activeFlinch?.intensity ?? 0};"
						in:fade={{ duration: 600, delay: 200 }}
						out:fade={{ duration: 400 }}
						onanimationend={consumeFlinch}
					>
						<div
							class="prose-nyx"
							class:prose-advance={visibleIndex < paragraphs.length - 1}
							onclick={advanceText}
							role="presentation"
						>
							{@html renderProse(paragraphs[visibleIndex] ?? '')}
						</div>
					</div>
				{/key}
			{/if}

			{#if !$isProcessing && ($repairWitness || trace)}
				<div class="mb-6 max-w-2xl mx-auto fade-in">
					<details class="border border-[var(--nyx-border)]/60 bg-black/20 px-4 py-3">
						<summary
							class="cursor-pointer text-[10px] uppercase tracking-[0.22em]"
							style="font-family: var(--font-mono); color: var(--nyx-text-dim);"
						>
							The Fates Deliberated
						</summary>

						<div class="mt-4 flex flex-col gap-3">
							{#if $repairWitness}
								<p
									class="text-xs leading-relaxed"
									style="font-family: var(--font-prose); color: var(--nyx-oracle-gold);"
								>
									{$repairWitness}
								</p>
							{/if}

							{#if trace?.final_reason}
								<p
									class="text-sm leading-relaxed"
									style="font-family: var(--font-prose); color: var(--nyx-text-dim);"
								>
									{trace.final_reason}
								</p>
							{/if}

							{#if $gameState?.canon?.current_scene?.immediate_problem}
								<p
									class="text-xs leading-relaxed"
									style="font-family: var(--font-prose); color: var(--nyx-text);"
								>
									Immediate problem: {$gameState.canon.current_scene.immediate_problem}
								</p>
							{/if}

							{#if trace && trace.winner_order.length > 0}
								<div class="flex flex-wrap gap-2">
									{#each trace.winner_order as fate}
										<span
											class="px-2 py-1 text-[10px] uppercase tracking-[0.16em] border border-[var(--nyx-border)]/60"
											style="font-family: var(--font-mono); color: var(--nyx-text-dim);"
										>
											{fate}
										</span>
									{/each}
								</div>
							{/if}

							{#if witnessProposals.length > 0}
								<div class="flex flex-col gap-2">
									{#each witnessProposals as proposal}
										<p
											class="text-xs leading-relaxed"
											style="font-family: var(--font-prose); color: var(--nyx-text-dim);"
										>
											<span style="color: var(--nyx-text);">{proposal.agent}:</span>
											{proposal.intervention_copy || proposal.refusal_reason || proposal.priority_note}
										</p>
									{/each}
								</div>
							{/if}
						</div>
					</details>
				</div>
			{/if}

			<!-- Controls container (auto height for choice buttons) -->
			<div class="mt-8 flex flex-col gap-4 items-center justify-center">
				{#if $isTerminal}
					<!-- The Death Rite overlay owns this moment -->
				{:else if paragraphs.length > 0 && visibleIndex < paragraphs.length - 1 && !$isProcessing}
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
									onclick={() => {
										submitAction(choice).catch((err) => {
											console.error('[nyx] Choice action failed:', err);
										});
									}}
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

	<!-- The Death Rite (terminal overlay — severance, epitaph, the book) -->
	{#if $isTerminal}
		<DeathRite />
	{/if}

	<!-- Dream Overlay (Hypnos epoch-boundary interlude) -->
	{#if $activeDream}
		<div
			class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
			transition:fade={{ duration: 800 }}
		>
			<div class="max-w-lg px-8 text-center">
				<p class="hypnos-text text-lg leading-relaxed mb-8">
					{$activeDream}
				</p>
				{#if ($gameState?.ledger ?? []).some((p) => p.status === 'planted' || p.status === 'promoted')}
					<p
						class="mb-6 text-xs italic"
						style="font-family: var(--font-prose); color: var(--nyx-text-dim); opacity: 0.7;"
					>
						The dream knows the story's debts.
					</p>
				{/if}
				<button
					onclick={dismissDream}
					class="text-[var(--nyx-text-dim)] hover:text-[var(--nyx-text)] transition-colors"
					style="font-family: var(--font-prose); font-size: 0.875rem; letter-spacing: 0.1em;"
				>
					[ Awaken ]
				</button>
			</div>
		</div>
	{/if}
</main>
