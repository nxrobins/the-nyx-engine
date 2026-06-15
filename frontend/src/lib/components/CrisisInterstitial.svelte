<!--
  CrisisInterstitial — the in-flow care surface (SAFE-C6/C9).

  Opens on its OWN store (`crisisInterstitial`), set either by the server's
  position-0 `crisis_resources` SSE frame (gate-on) or by a CrisisLink click
  (always available). It NEVER reads $gameState / isTerminal / proseHistory, so
  turn outcome cannot suppress it. Mounted at the top level of +page.svelte at
  z-200 — above DeathRite (z-60), the book reader (z-70), and every pane — and
  it PERSISTS until the player explicitly dismisses it (no auto-dismiss timer),
  so on a self-destruction death the card is co-visible with the death render.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import { crisisInterstitial, dismissCrisis } from '$lib/stores/engine';
</script>

{#if $crisisInterstitial}
	{@const r = $crisisInterstitial}
	<div
		class="crisis-overlay"
		transition:fade={{ duration: 250 }}
		role="dialog"
		aria-modal="true"
		aria-label="Crisis resources"
	>
		<div class="crisis-card">
			<p class="crisis-title">{r.title}</p>
			{#if r.body}
				<p class="crisis-body">{r.body}</p>
			{/if}
			<ul class="crisis-resources">
				{#each r.resources as res}
					<li class="crisis-resource">
						<span class="crisis-resource-label">{res.label}</span>
						<span class="crisis-resource-detail">{res.detail}</span>
					</li>
				{/each}
			</ul>
			{#if r.disclaimer}
				<p class="crisis-disclaimer">{r.disclaimer}</p>
			{/if}
			<button type="button" class="crisis-dismiss" onclick={dismissCrisis}>
				Return to the story
			</button>
		</div>
	</div>
{/if}
