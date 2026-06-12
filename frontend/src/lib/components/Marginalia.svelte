<!--
  Marginalia — present-NPC portraits in the left margin (The Ink, Layer 1).
  Decorative only: pointer-events none, aria-hidden, hidden below 1100px.
  Deterministic: present_npc_ids sorted by id, first 4 with plates. An NPC
  without a portrait simply isn't drawn — absence renders nothing.
-->
<script lang="ts">
	import { gameState } from '$lib/stores/engine';
	import { plateManifest } from '$lib/stores/plates';

	let portraits = $derived.by(() => {
		const ids = $gameState?.canon?.current_scene?.present_npc_ids ?? [];
		const manifest = $plateManifest;
		const npcs = $gameState?.canon?.npcs ?? {};
		return [...ids]
			.sort()
			.filter((id) => Boolean(manifest[id]))
			.slice(0, 4)
			.map((id) => ({ id, url: manifest[id], name: npcs[id]?.name ?? '' }));
	});
</script>

{#if portraits.length > 0}
	<div class="marginalia" aria-hidden="true">
		{#each portraits as portrait (portrait.id)}
			<div class="marginalia-frame">
				<img src={portrait.url} alt="" loading="lazy" />
			</div>
		{/each}
	</div>
{/if}
