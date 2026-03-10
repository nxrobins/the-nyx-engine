<!--
  Turn 0: Hamartia Selection Screen
  Dead-center on pure black. Five choices. No going back.
-->
<script lang="ts">
	import { initGame, fetchHamartiaOptions } from '$lib/stores/engine';

	let options = $state<string[]>([]);
	let selected = $state<string>('');
	let loading = $state(false);
	let fading = $state(false);
	let error = $state('');

	// Fetch options on mount
	$effect(() => {
		fetchHamartiaOptions()
			.then((opts) => { options = opts; })
			.catch(() => {
				// Fallback if backend isn't ready
				options = [
					'Hubris of the Intellect',
					'Wrath of the Untempered',
					'Avarice Unbound',
					'Cowardice Veiled as Wisdom',
					'Pride That Blinds',
				];
			});
	});

	async function choose(hamartia: string) {
		if (loading) return;
		selected = hamartia;
		loading = true;
		error = '';

		try {
			await initGame(hamartia);
			fading = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'The Fates refuse this thread.';
			loading = false;
			selected = '';
		}
	}
</script>

<div class="init-screen" class:init-fade-out={fading}>
	<div class="flex flex-col items-center gap-12 max-w-lg px-6">
		<!-- Title -->
		<div class="text-center">
			<h1
				class="text-4xl tracking-[0.2em] uppercase mb-3"
				style="font-family: var(--font-prose); font-weight: 600; color: var(--nyx-text);"
			>
				NYX ENGINE
			</h1>
			<p class="text-sm tracking-widest uppercase" style="color: var(--nyx-text-dim);">
				Choose your Doom
			</p>
		</div>

		<!-- Hamartia Options -->
		<div class="flex flex-col gap-3 w-full">
			{#each options as option}
				<button
					onclick={() => choose(option)}
					disabled={loading}
					class="group relative w-full text-left px-6 py-4 border transition-all duration-300
						{selected === option
							? 'border-[var(--nyx-oracle-gold)] bg-[var(--nyx-oracle-gold)]/5'
							: 'border-[var(--nyx-border)] hover:border-[var(--nyx-text-dim)]'}
						disabled:opacity-40 disabled:cursor-not-allowed"
				>
					<span
						class="text-lg tracking-wide transition-colors duration-300
							{selected === option ? 'text-[var(--nyx-oracle-gold)]' : 'text-[var(--nyx-text)] group-hover:text-white'}"
						style="font-family: var(--font-prose);"
					>
						{option}
					</span>
				</button>
			{/each}
		</div>

		<!-- Loading / Error -->
		{#if loading}
			<p class="text-sm italic" style="color: var(--nyx-text-dim); font-family: var(--font-prose);">
				The Fates weave your thread...
			</p>
		{/if}

		{#if error}
			<p class="text-sm text-red-400">{error}</p>
		{/if}
	</div>
</div>
