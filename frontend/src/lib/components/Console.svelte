<!--
  Player Input Console — v2.0
  Fixed to the bottom of TheThread center pane.
  Minimal, borderless, sumi-e aesthetic.
-->
<script lang="ts">
	import { submitAction, isProcessing, gameState } from '$lib/stores/engine';

	let inputText = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);
	let error = $state('');

	// THE PULSE: in adulthood the console opens only at crucibles — the full
	// council is awake. The cue is felt, not announced (Phase 1 ruling: flow
	// is presentation too).
	const fatesLeanIn = $derived(
		$gameState?.session?.epoch_phase === 4 &&
		$gameState?.session?.beat_kind === 'crucible'
	);

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
</script>

<!-- Terminal state is owned by the Death Rite overlay, not the console. -->
<div class="relative z-10 px-8 py-4" class:fates-lean-in={fatesLeanIn}>
	<form onsubmit={handleSubmit} class="flex gap-3 items-center">
			<input
				bind:this={inputEl}
				bind:value={inputText}
				onkeydown={handleKeydown}
				disabled={$isProcessing}
				placeholder={$isProcessing
					? 'The Fates deliberate...'
					: fatesLeanIn
						? 'The Fates lean in. What do you do?'
						: 'What do you do?'}
				class="flex-1 bg-transparent border-b border-[var(--nyx-border)] px-2 py-2
					text-[var(--nyx-text)] placeholder:text-[var(--nyx-text-dim)]/50
					focus:outline-none focus-visible:border-[var(--nyx-oracle-gold)]
					disabled:opacity-30 transition-colors"
				style="font-family: var(--font-prose); font-size: 1rem;"
			/>
			<button
				type="submit"
				disabled={$isProcessing || !inputText.trim()}
				class="text-xs uppercase tracking-[0.15em] px-3 py-2
					text-[var(--nyx-text-dim)] hover:text-[var(--nyx-text)]
					focus:outline-none focus-visible:text-[var(--nyx-text)]
					focus-visible:underline underline-offset-4
					disabled:opacity-20 transition-colors"
				style="font-family: var(--font-mono);"
			>
				{$isProcessing ? '...' : 'Act'}
			</button>
		</form>
		{#if error}
			<p class="text-red-400 text-xs mt-2">{error}</p>
		{/if}
</div>
