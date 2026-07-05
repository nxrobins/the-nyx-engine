<!--
  Nyx Engine v3.0 — Main Game Interface
  Vestibule router: Title → Incarnation → Playing.
  Center-only layout with collapsible side pane overlays.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import TitleScreen from '$lib/components/TitleScreen.svelte';
	import ConsentGate from '$lib/components/ConsentGate.svelte';
	import Incarnation from '$lib/components/Incarnation.svelte';
	import SoulLedger from '$lib/components/SoulLedger.svelte';
	import TheThread from '$lib/components/TheThread.svelte';
	import TheOracle from '$lib/components/TheOracle.svelte';
	import InkWeather from '$lib/components/InkWeather.svelte';
	import CrisisLink from '$lib/components/CrisisLink.svelte';
	import CrisisInterstitial from '$lib/components/CrisisInterstitial.svelte';
	import { vestibuleState, loadSafety } from '$lib/stores/vestibule';
	import { gameState, mechanicToast, resumeGame } from '$lib/stores/engine';

	// The Vigil: hydrate the care gate once on boot (fail-closed → off).
	onMount(async () => {
		loadSafety();
		// Durability (THE THREAD PERSISTS): if a thread was left running when the
		// tab closed, rehydrate it from its stored token and go straight to play —
		// a refresh no longer orphans a living life. A terminal thread resumes into
		// the Death Rite (permanence survives the refresh).
		if (await resumeGame()) {
			vestibuleState.set('playing');
		}
	});

	let leftOpen = $state(false);
	let rightOpen = $state(false);

	// UX-C9: keyboard reachability for the mechanics panes. Opening moves focus
	// INTO the pane (otherwise the edge is discoverable but the pane is a
	// keyboard dead-end); Escape closes; closing returns focus to the opener.
	let leftPaneEl: HTMLDivElement | null = $state(null);
	let rightPaneEl: HTMLDivElement | null = $state(null);
	let leftEdgeEl: HTMLButtonElement | null = $state(null);
	let rightEdgeEl: HTMLButtonElement | null = $state(null);
	let lastOpener: HTMLElement | null = null;

	async function openLeft() {
		leftOpen = true;
		lastOpener = leftEdgeEl;
		await tick();
		leftPaneEl?.focus();
	}

	async function openRight() {
		rightOpen = true;
		lastOpener = rightEdgeEl;
		await tick();
		rightPaneEl?.focus();
	}

	function dismissPanes() {
		const wasOpen = leftOpen || rightOpen;
		leftOpen = false;
		rightOpen = false;
		if (wasOpen) {
			lastOpener?.focus();
			lastOpener = null;
		}
	}

	function handlePaneKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && (leftOpen || rightOpen)) {
			e.preventDefault();
			dismissPanes();
		}
	}

	/** The Witness: doom dread on the HUD */
	let doom = $derived($gameState?.doom ?? null);
	let doomPips = $derived(
		doom?.active
			? '●'.repeat(Math.min(doom.stage, doom.max_stage)) +
				'○'.repeat(Math.max(doom.max_stage - doom.stage, 0))
			: ''
	);

	/** The Witness: pane-edge pulses when their contents change unseen */
	let leftPulse = $state(false);
	let rightPulse = $state(false);
	$effect(() => {
		if ($mechanicToast && !leftOpen) {
			leftPulse = true;
			setTimeout(() => (leftPulse = false), 2200);
			if (($mechanicToast.nemesis_struck || $mechanicToast.eris_struck) && !rightOpen) {
				rightPulse = true;
				setTimeout(() => (rightPulse = false), 2200);
			}
		}
	});
</script>

<!-- UX-C9: Escape closes an open mechanics pane (guarded to playing state). -->
<svelte:window onkeydown={handlePaneKeydown} />

{#if $vestibuleState === 'title'}
	<TitleScreen />
{:else if $vestibuleState === 'consent'}
	<ConsentGate />
{:else if $vestibuleState === 'incarnation'}
	<Incarnation />
{:else}
	<!-- Game UI (playing state) -->

	<!-- Diegetic Thread-Line HUD -->
	{#if $gameState}
		<div class="thread-hud" class:doomed={doom?.active}>
			<span class="thread-hud-text">
				{$gameState.session.player_name}
				<span class="thread-hud-separator">✦</span>
				AGE {$gameState.session.player_age}
				<span class="thread-hud-separator">✦</span>
				{$gameState.soul_ledger.hamartia}
				{#if doom?.active}
					<span class="thread-hud-separator">✦</span>
					<span class="doom-pips" title={doom.description}>✂ {doomPips}</span>
				{/if}
			</span>
		</div>
	{/if}

	<!-- Edge triggers (always visible) -->
	<button
		type="button"
		bind:this={leftEdgeEl}
		class="pane-edge pane-edge-left"
		class:edge-pulse={leftPulse}
		aria-label="Open soul ledger"
		onclick={openLeft}
	>
		<span class="edge-glyph" aria-hidden="true">‹</span>
	</button>
	<button
		type="button"
		bind:this={rightEdgeEl}
		class="pane-edge pane-edge-right"
		class:edge-pulse={rightPulse}
		aria-label="Open oracle"
		onclick={openRight}
	>
		<span class="edge-glyph" aria-hidden="true">›</span>
	</button>

	<!-- Dismiss overlay (when either pane is open) -->
	{#if leftOpen || rightOpen}
		<button
			type="button"
			class="pane-dismiss"
			aria-label="Dismiss side panes"
			onclick={dismissPanes}
		></button>
	{/if}

	<!-- Side pane overlays -->
	<div
		bind:this={leftPaneEl}
		class="pane-overlay pane-overlay-left"
		class:open={leftOpen}
		tabindex="-1"
	>
		<SoulLedger />
	</div>
	<div
		bind:this={rightPaneEl}
		class="pane-overlay pane-overlay-right"
		class:open={rightOpen}
		tabindex="-1"
	>
		<TheOracle />
	</div>

	<!-- The Ink: ambient weather (fixed sibling of the grid — never inside
	     it; the fade-in stacking context would trap a fixed child) -->
	<InkWeather />

	<!-- Center pane (full width) -->
	<div class="game-grid fade-in">
		<TheThread />
	</div>

	<!-- Mechanic Toast (Phase 1 feedback) -->
	{#if $mechanicToast}
		<div class="mechanic-toast" class:nemesis={$mechanicToast.nemesis_struck} class:eris={$mechanicToast.eris_struck}>
			{#if $mechanicToast.nemesis_struck}
				<span class="toast-icon">&#x2620;</span>
				<span>NEMESIS STRIKES</span>
			{:else if $mechanicToast.eris_struck}
				<span class="toast-icon">&#x2604;</span>
				<span>ERIS INTERVENES</span>
			{:else if !$mechanicToast.valid}
				<span class="toast-icon">&#x2717;</span>
				<span>{$mechanicToast.dominant} CHECK FAILED</span>
			{:else}
				<span class="toast-icon">&#x2719;</span>
				<span>{$mechanicToast.dominant}</span>
				{#each Object.entries($mechanicToast.vector_deltas) as [vec, delta]}
					{#if delta !== 0}
						<span class="toast-delta" class:positive={delta > 0} class:negative={delta < 0}>
							{delta > 0 ? '+' : ''}{delta} {vec}
						</span>
					{/if}
				{/each}
			{/if}
		</div>
	{/if}
{/if}

<!-- The Vigil: always-on, gate-independent affordances. Mounted at the top level
     (outside the phase ladder) so the link is on EVERY screen (SAFE-C8) and the
     interstitial SURVIVES DeathRite, which lives inside the playing branch — it
     renders above all surfaces and persists until an explicit dismissal (C9). -->
<CrisisLink />
<CrisisInterstitial />
