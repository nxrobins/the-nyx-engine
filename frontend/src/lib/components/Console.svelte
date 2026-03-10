<!--
  Player Input Console — v2.0
  Fixed to the bottom of TheThread center pane.
  Minimal, borderless, sumi-e aesthetic.
-->
<script lang="ts">
	import { submitAction, isProcessing, isTerminal, resetGame } from '$lib/stores/engine';

	let inputText = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);
	let error = $state('');

	async function handleSubmit(e?: Event) {
		e?.preventDefault();
		const action = inputText.trim();
		if (!action || $isProcessing) return;

		error = '';
		inputText = '';

		try {
			await submitAction(action);
		} catch (e) {
			error = e instanceof Error ? e.message : 'The engine falters.';
		}

		inputEl?.focus();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSubmit();
		}
	}

	async function handleReset() {
		await resetGame();
		inputEl?.focus();
	}
</script>

<div class="relative z-10 px-8 py-4">
	{#if $isTerminal}
		<div class="text-center space-y-3">
			<p
				class="text-sm font-semibold"
				style="font-family: var(--font-prose); color: var(--nyx-nemesis);"
			>
				Your thread has been severed.
			</p>
			<button
				onclick={handleReset}
				class="px-5 py-2 text-sm border border-[var(--nyx-text-dim)] text-[var(--nyx-text)]
					hover:border-[var(--nyx-text)] hover:text-white transition-all duration-300"
				style="font-family: var(--font-prose); letter-spacing: 0.1em;"
			>
				Begin New Thread
			</button>
		</div>
	{:else}
		<form onsubmit={handleSubmit} class="flex gap-3 items-center">
			<input
				bind:this={inputEl}
				bind:value={inputText}
				onkeydown={handleKeydown}
				disabled={$isProcessing}
				placeholder={$isProcessing ? 'The Fates deliberate...' : 'What do you do?'}
				class="flex-1 bg-transparent border-b border-[var(--nyx-border)] px-2 py-2
					text-[var(--nyx-text)] placeholder:text-[var(--nyx-text-dim)]/50
					focus:outline-none focus:border-[var(--nyx-text-dim)]
					disabled:opacity-30 transition-colors"
				style="font-family: var(--font-prose); font-size: 1rem;"
			/>
			<button
				type="submit"
				disabled={$isProcessing || !inputText.trim()}
				class="text-xs uppercase tracking-[0.15em] px-3 py-2
					text-[var(--nyx-text-dim)] hover:text-[var(--nyx-text)]
					disabled:opacity-20 transition-colors"
				style="font-family: var(--font-mono);"
			>
				{$isProcessing ? '...' : 'Act'}
			</button>
		</form>
		{#if error}
			<p class="text-red-400 text-xs mt-2">{error}</p>
		{/if}
	{/if}
</div>
