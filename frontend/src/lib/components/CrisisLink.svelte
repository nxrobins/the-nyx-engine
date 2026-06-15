<!--
  CrisisLink — the always-on, gate-independent help affordance (SAFE-C3/C8).
  Mounted ONCE at the top level of +page.svelte, so it is structurally present
  on every screen (title, consent, incarnation, playing, AND above DeathRite) —
  a person is never one screen away from no affordance. It opens the interstitial
  with the hardcoded client copy; it needs no network and no `reviewed` flag.

  DECIDED (Nigel): this minimal link renders BY DEFAULT — the one approved
  exception to "nothing shows until the gate is flipped", because gating the only
  backstop off would defeat the feature.
-->
<script lang="ts">
	import { openCrisis } from '$lib/stores/engine';
	import { CRISIS_FALLBACK } from '$lib/safety';
</script>

<button
	type="button"
	class="crisis-link"
	onclick={() => openCrisis(CRISIS_FALLBACK)}
>
	In crisis? Find help now.
</button>
