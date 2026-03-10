<!--
  Left Pane (280px): Soul Ledger
  Displays hamartia badge, four soul vectors, and active oaths.
-->
<script lang="ts">
	import { gameState } from '$lib/stores/engine';
	import type { SoulVectors, Oath } from '$lib/types/engine';

	let vectors = $derived<SoulVectors | null>(
		$gameState?.soul_ledger.vectors ?? null
	);

	let hamartia = $derived<string>(
		$gameState?.soul_ledger.hamartia ?? ''
	);

	let oaths = $derived<Oath[]>(
		$gameState?.soul_ledger.active_oaths ?? []
	);

	/** Format a vector value as whole number */
	function fmt(val: number): string {
		return Math.round(val).toString();
	}

	/** Vector label pairs for rendering */
	const vectorKeys: { key: keyof SoulVectors; label: string }[] = [
		{ key: 'metis', label: 'CUNNING' },
		{ key: 'bia', label: 'FORCE' },
		{ key: 'kleos', label: 'RENOWN' },
		{ key: 'aidos', label: 'SHADOW' },
	];

	/** Color based on vector value */
	function vectorColor(val: number): string {
		if (val >= 9) return 'text-[var(--nyx-oracle-gold)]';
		if (val >= 7) return 'text-white';
		if (val <= 1) return 'text-red-500/60';
		if (val <= 3) return 'text-[var(--nyx-text-dim)]';
		return 'text-[var(--nyx-text)]';
	}
</script>

<aside class="h-full overflow-y-auto border-r border-[var(--nyx-border)] px-5 py-6 flex flex-col gap-8 bg-[var(--nyx-void)]">
	<!-- Hamartia Badge -->
	{#if hamartia}
		<div class="text-center">
			<p class="text-[10px] uppercase tracking-[0.25em] mb-2" style="color: var(--nyx-text-dim);">
				Tragic Flaw
			</p>
			<p
				class="text-sm italic tracking-wide"
				style="font-family: var(--font-prose); color: var(--nyx-oracle-gold);"
			>
				{hamartia}
			</p>
		</div>
	{/if}

	<!-- Soul Vectors -->
	{#if vectors}
		<div class="flex flex-col gap-4">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				Soul Vectors
			</p>

			{#each vectorKeys as { key, label }}
				{@const val = vectors[key]}
				<div class="flex items-center justify-between gap-3">
					<span
						class="text-xs tracking-[0.15em] w-16"
						style="font-family: var(--font-mono); color: var(--nyx-text-dim);"
					>
						{label}
					</span>

					<!-- Thin bar -->
					<div class="flex-1 h-[2px] bg-[var(--nyx-border)] relative">
						<div
							class="absolute inset-y-0 left-0 transition-all duration-700 ease-out
								{val >= 9 ? 'bg-[var(--nyx-oracle-gold)]' : 'bg-[var(--nyx-text)]'}"
							style="width: {(val / 10) * 100}%;"
						></div>
					</div>

					<!-- Value -->
					<span
						class="text-xs tabular-nums w-8 text-right transition-colors duration-500 {vectorColor(val)}"
						style="font-family: var(--font-mono);"
					>
						{fmt(val)}
					</span>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Active Oaths -->
	{#if oaths.length > 0}
		<div class="flex flex-col gap-3">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				Oaths Sworn
			</p>

			{#each oaths as oath}
				<div
					class="text-sm leading-relaxed pl-3 border-l-2 transition-all duration-300
						{oath.broken
							? 'border-[var(--nyx-oracle-gold)] kintsugi kintsugi-line'
							: 'border-[var(--nyx-border)]'}"
					style="font-family: var(--font-prose);"
				>
					<p class={oath.broken ? 'text-[var(--nyx-oracle-gold)]/70' : 'text-[var(--nyx-text)]'}>
						"{oath.text}"
					</p>
					<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
						Turn {oath.turn_sworn}{oath.broken ? ' — BROKEN' : ''}
					</p>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Spacer to push content up naturally -->
	<div class="flex-1"></div>
</aside>
