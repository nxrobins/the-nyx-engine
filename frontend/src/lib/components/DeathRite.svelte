<!--
  The Death Rite — the most important screen in a permadeath game.
  Click-paced stages: severance → the carved epitaph → the soul at the
  severing → the binding (open the book) → return to the Tapestry.
  Death stops being a failure state and becomes authorship.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import {
		deathReason,
		epitaph,
		bookId,
		gameState,
		resetGame,
	} from '$lib/stores/engine';
	import BookReader from './BookReader.svelte';

	let stage = $state(0);
	let readerOpen = $state(false);
	let returning = $state(false);

	const STAGES = 3; // 0 severance, 1 epitaph, 2 soul, 3 binding (final)

	function advance() {
		if (stage < STAGES) stage++;
	}

	async function returnToTapestry() {
		if (returning) return;
		returning = true;
		await resetGame();
	}

	let vectors = $derived($gameState?.soul_ledger.vectors ?? null);
	let hamartia = $derived($gameState?.soul_ledger.hamartia ?? '');
	let lifeVoice = $derived($gameState?.life_voice ?? '');

	const vectorRows: { key: 'metis' | 'bia' | 'kleos' | 'aidos'; label: string }[] = [
		{ key: 'metis', label: 'CUNNING' },
		{ key: 'bia', label: 'FORCE' },
		{ key: 'kleos', label: 'RENOWN' },
		{ key: 'aidos', label: 'SHADOW' }
	];
</script>

<div class="death-rite-overlay" transition:fade={{ duration: 900 }}>
	{#if stage < STAGES}
		<!-- Click-paced stages -->
		<button class="death-rite-stage" onclick={advance} aria-label="Continue the rite">
			{#if stage === 0}
				<div class="death-rite-content" in:fade={{ duration: 700 }}>
					<p class="death-rite-kicker">THE THREAD IS SEVERED</p>
					<p class="death-rite-body">{$deathReason}</p>
				</div>
			{:else if stage === 1}
				<div class="death-rite-content" in:fade={{ duration: 700 }}>
					<p class="death-rite-kicker">THE STONE READS</p>
					<blockquote class="epitaph-card">
						{$epitaph || 'A thread lost to silence.'}
					</blockquote>
				</div>
			{:else}
				<div class="death-rite-content" in:fade={{ duration: 700 }}>
					<p class="death-rite-kicker">THE SOUL AT THE SEVERING</p>
					{#if hamartia}
						<p class="death-rite-flaw">{hamartia}</p>
					{/if}
					{#if vectors}
						<div class="death-rite-vectors">
							{#each vectorRows as { key, label }}
								<div class="death-rite-vector-row">
									<span class="death-rite-vector-label">{label}</span>
									<span class="death-rite-vector-value">{Math.round(vectors[key])}</span>
								</div>
							{/each}
						</div>
					{/if}
					{#if lifeVoice}
						<p class="death-rite-voice">Written in this voice: {lifeVoice}</p>
					{/if}
				</div>
			{/if}
			<p class="death-rite-continue">·</p>
		</button>
	{:else}
		<!-- Final stage: the binding -->
		<div class="death-rite-content" in:fade={{ duration: 700 }}>
			{#if $bookId}
				<p class="death-rite-kicker">THE SCRIBE HAS BOUND THIS LIFE</p>
				<p class="death-rite-body death-rite-body-dim">
					Somewhere in the dark, pages were turning all along.
				</p>
				<div class="death-rite-actions">
					<button class="death-rite-btn death-rite-btn-gold" onclick={() => (readerOpen = true)}>
						[ Open the Book ]
					</button>
					<button class="death-rite-btn" onclick={returnToTapestry} disabled={returning}>
						[ Return to the Tapestry ]
					</button>
				</div>
			{:else}
				<p class="death-rite-kicker">THIS LIFE GOES UNBOUND</p>
				<p class="death-rite-body death-rite-body-dim">
					No scribe finished the pages. The Tapestry will remember what the shelf cannot.
				</p>
				<div class="death-rite-actions">
					<button class="death-rite-btn" onclick={returnToTapestry} disabled={returning}>
						[ Return to the Tapestry ]
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

{#if readerOpen && $bookId}
	<BookReader bookId={$bookId} onClose={() => (readerOpen = false)} />
{/if}
