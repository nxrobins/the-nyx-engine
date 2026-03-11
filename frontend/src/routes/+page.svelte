<!--
  Nyx Engine v3.0 — Main Game Interface
  Vestibule router: Title → Incarnation → Playing.
  Center-only layout with collapsible side pane overlays.
-->
<script lang="ts">
	import TitleScreen from '$lib/components/TitleScreen.svelte';
	import Incarnation from '$lib/components/Incarnation.svelte';
	import SoulLedger from '$lib/components/SoulLedger.svelte';
	import TheThread from '$lib/components/TheThread.svelte';
	import TheOracle from '$lib/components/TheOracle.svelte';
	import { vestibuleState } from '$lib/stores/vestibule';
	import { gameState, mechanicToast } from '$lib/stores/engine';

	let leftOpen = $state(false);
	let rightOpen = $state(false);

	function dismissPanes() {
		leftOpen = false;
		rightOpen = false;
	}

	/** Beat position indicator for dev overlay (optional future use) */
</script>

{#if $vestibuleState === 'title'}
	<TitleScreen />
{:else if $vestibuleState === 'incarnation'}
	<Incarnation />
{:else}
	<!-- Game UI (playing state) -->

	<!-- Diegetic Thread-Line HUD -->
	{#if $gameState}
		<div class="thread-hud">
			<span class="thread-hud-text">
				{$gameState.session.player_name}
				<span class="thread-hud-separator">✦</span>
				AGE {$gameState.session.player_age}
				<span class="thread-hud-separator">✦</span>
				{$gameState.session.hamartia}
			</span>
		</div>
	{/if}

	<!-- Edge triggers (always visible) -->
	<div class="pane-edge pane-edge-left" onclick={() => leftOpen = true}>
		<span class="edge-glyph">‹</span>
	</div>
	<div class="pane-edge pane-edge-right" onclick={() => rightOpen = true}>
		<span class="edge-glyph">›</span>
	</div>

	<!-- Dismiss overlay (when either pane is open) -->
	{#if leftOpen || rightOpen}
		<div class="pane-dismiss" onclick={dismissPanes}></div>
	{/if}

	<!-- Side pane overlays -->
	<div class="pane-overlay pane-overlay-left" class:open={leftOpen}>
		<SoulLedger />
	</div>
	<div class="pane-overlay pane-overlay-right" class:open={rightOpen}>
		<TheOracle />
	</div>

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
