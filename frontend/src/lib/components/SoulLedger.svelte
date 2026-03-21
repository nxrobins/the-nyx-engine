<!--
  Left Pane: Soul Ledger
  Displays hamartia, vectors, pressure, oaths, and legacy residue.
-->
<script lang="ts">
	import { gameState } from '$lib/stores/engine';
	import type { LegacyEcho, Oath, PressureState, SoulVectors } from '$lib/types/engine';

	let vectors = $derived<SoulVectors | null>($gameState?.soul_ledger.vectors ?? null);
	let hamartia = $derived<string>($gameState?.soul_ledger.hamartia ?? '');
	let oaths = $derived<Oath[]>($gameState?.soul_ledger.active_oaths ?? []);
	let pressures = $derived<PressureState | null>($gameState?.pressures ?? null);
	let legacyEchoes = $derived<LegacyEcho[]>($gameState?.legacy_echoes ?? []);

	function fmt(val: number): string {
		return Math.round(val).toString();
	}

	const vectorKeys: { key: keyof SoulVectors; label: string }[] = [
		{ key: 'metis', label: 'CUNNING' },
		{ key: 'bia', label: 'FORCE' },
		{ key: 'kleos', label: 'RENOWN' },
		{ key: 'aidos', label: 'SHADOW' }
	];

	function vectorColor(val: number): string {
		if (val >= 9) return 'text-[var(--nyx-oracle-gold)]';
		if (val >= 7) return 'text-white';
		if (val <= 1) return 'text-red-500/60';
		if (val <= 3) return 'text-[var(--nyx-text-dim)]';
		return 'text-[var(--nyx-text)]';
	}

	const pressureKeys: { key: keyof PressureState; label: string }[] = [
		{ key: 'suspicion', label: 'SUSPICION' },
		{ key: 'scarcity', label: 'SCARCITY' },
		{ key: 'wounds', label: 'WOUNDS' },
		{ key: 'debt', label: 'DEBT' },
		{ key: 'faction_heat', label: 'FACTION' },
		{ key: 'omen', label: 'OMEN' }
	];

	let dominantPressure = $derived.by(() => {
		if (!pressures) return null;
		const entries = pressureKeys
			.map(({ key, label }) => ({ key, label, value: pressures[key] }))
			.filter((entry) => typeof entry.value === 'number' && entry.value >= 0.4)
			.sort((a, b) => Number(b.value) - Number(a.value));
		return entries[0] ?? null;
	});

	function oathTone(status: string): string {
		if (status === 'broken') return 'var(--nyx-nemesis)';
		if (status === 'fulfilled') return 'var(--nyx-oracle-gold)';
		if (status === 'transformed') return 'var(--nyx-text)';
		return 'var(--nyx-text-dim)';
	}
</script>

<aside class="h-full overflow-y-auto border-r border-[var(--nyx-border)] px-5 py-6 flex flex-col gap-8 bg-[var(--nyx-void)]">
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

	{#if legacyEchoes.length > 0}
		<div class="flex flex-col gap-3">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				Legacy Echo
			</p>

			{#each legacyEchoes as echo}
				<div
					class="text-sm leading-relaxed pl-3 border-l-2 border-[var(--nyx-oracle-gold)]/50"
					style="font-family: var(--font-prose);"
				>
					<p class="text-[var(--nyx-oracle-gold)]/90">{echo.inherited_mark}</p>
					<p class="text-[var(--nyx-text-dim)] text-xs mt-1">{echo.mechanical_effect}</p>
				</div>
			{/each}
		</div>
	{/if}

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

					<div class="flex-1 h-[2px] bg-[var(--nyx-border)] relative">
						<div
							class="absolute inset-y-0 left-0 transition-all duration-700 ease-out
								{val >= 9 ? 'bg-[var(--nyx-oracle-gold)]' : 'bg-[var(--nyx-text)]'}"
							style="width: {(val / 10) * 100}%;"
						></div>
					</div>

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

	{#if pressures}
		<div class="flex flex-col gap-3">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				World Pressure
			</p>

			{#each pressureKeys as { key, label }}
				{@const val = pressures[key]}
				{#if typeof val === 'number' && val >= 0.4}
					<div class="flex items-center justify-between gap-3">
						<span
							class="text-xs tracking-[0.15em] w-20"
							style="font-family: var(--font-mono); color: var(--nyx-text-dim);"
						>
							{label}
						</span>
						<div class="flex-1 h-[2px] bg-[var(--nyx-border)] relative">
							<div
								class="absolute inset-y-0 left-0 bg-[var(--nyx-oracle-gold)]/70 transition-all duration-700 ease-out"
								style="width: {(Math.min(val, 5) / 5) * 100}%;"
							></div>
						</div>
						<span
							class="text-xs tabular-nums w-8 text-right text-[var(--nyx-text)]"
							style="font-family: var(--font-mono);"
						>
							{val.toFixed(1)}
						</span>
					</div>
				{/if}
			{/each}

			{#if pressures.stability_streak >= 2}
				<p class="text-[10px] leading-relaxed" style="color: var(--nyx-text-dim);">
					Stability streak {pressures.stability_streak} means the world is waiting to break its calm.
				</p>
			{/if}

			{#if dominantPressure}
				<p class="text-[10px] leading-relaxed" style="color: var(--nyx-text-dim);">
					The loudest pressure is {dominantPressure.label.toLowerCase()} ({Number(dominantPressure.value).toFixed(1)}).
				</p>
			{:else}
				<p class="text-[10px] leading-relaxed" style="color: var(--nyx-text-dim);">
					No worldly force dominates the scene yet.
				</p>
			{/if}
		</div>
	{/if}

	{#if oaths.length > 0}
		<div class="flex flex-col gap-3">
			<p class="text-[10px] uppercase tracking-[0.25em]" style="color: var(--nyx-text-dim);">
				Oaths Sworn
			</p>

			{#each oaths as oath}
				<div
					class="text-sm leading-relaxed pl-3 border-l-2 transition-all duration-300
						{oath.status === 'broken'
							? 'border-[var(--nyx-oracle-gold)] kintsugi kintsugi-line'
							: 'border-[var(--nyx-border)]'}"
					style="font-family: var(--font-prose);"
				>
					<p class={oath.status === 'broken' ? 'text-[var(--nyx-oracle-gold)]/70' : 'text-[var(--nyx-text)]'}>
						"{oath.text}"
					</p>
					<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
						Turn {oath.turn_sworn} -
						<span style="color: {oathTone(oath.status)};">{oath.status.toUpperCase()}</span>
					</p>
					{#if oath.terms?.protected_target}
						<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
							Guarding: {oath.terms.protected_target}
						</p>
					{/if}
					{#if oath.terms?.deadline}
						<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
							Deadline: {oath.terms.deadline}
						</p>
					{/if}
					{#if oath.terms?.price}
						<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
							Price: {oath.terms.price}
						</p>
					{/if}
					{#if oath.terms?.witness}
						<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
							Witness: {oath.terms.witness}
						</p>
					{/if}
					{#if oath.fulfillment_note}
						<p class="text-[10px] mt-1" style="color: var(--nyx-text-dim);">
							{oath.fulfillment_note}
						</p>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<div class="flex-1"></div>
</aside>
