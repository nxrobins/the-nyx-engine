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

	let leftOpen = $state(false);
	let rightOpen = $state(false);

	function dismissPanes() {
		leftOpen = false;
		rightOpen = false;
	}
</script>

{#if $vestibuleState === 'title'}
	<TitleScreen />
{:else if $vestibuleState === 'incarnation'}
	<Incarnation />
{:else}
	<!-- Game UI (playing state) -->

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
{/if}
