<!--
  ConsentGate — content warning + self-asserted acknowledgement, shown first-run
  only when the care gate is reviewed (safetyReviewed && no current consent).
  While the gate is off (the shipped default) this screen never appears and the
  flow is identical to today.

  The affirmation is self-asserted and stored per-device in localStorage — it is
  NOT a verified age wall, identity record, or shared-device handler (AG-C4),
  and the copy says so plainly. DRAFT — pending human review.
-->
<script lang="ts">
	import { vestibuleState, acceptConsent } from '$lib/stores/vestibule';
	import { openCrisis } from '$lib/stores/engine';
	import { CRISIS_FALLBACK } from '$lib/safety';

	let affirmed = $state(false);

	function proceed() {
		if (!affirmed) return;
		acceptConsent();
		vestibuleState.set('incarnation');
	}
</script>

<div class="consent-gate">
	<div class="consent-card step-enter">
		<p class="consent-kicker">BEFORE YOU BEGIN</p>
		<p class="consent-body">
			This is a story of permanent death, self-destruction, and a world indifferent to
			suffering. Threads end and do not return. If that is not what you want today, you are
			free to close this tab — no thread will be woven.
		</p>

		<label class="consent-affirm">
			<input type="checkbox" bind:checked={affirmed} />
			<span>I am 18 or older, and I understand.</span>
		</label>
		<p class="consent-note">
			A self-asserted acknowledgement, stored only on this device. It is not an identity
			check or an age verification.
		</p>

		<button class="consent-proceed" disabled={!affirmed} onclick={proceed}>
			Enter the Loom
		</button>

		<button type="button" class="consent-help" onclick={() => openCrisis(CRISIS_FALLBACK)}>
			In crisis? Find help now.
		</button>
	</div>
</div>
