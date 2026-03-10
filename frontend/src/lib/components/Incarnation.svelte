<!--
  Incarnation.svelte — Diegetic Character Creation
  Step 0: Name (text input) → Step 1: Gender (two buttons) → Step 2: First Memory (four archetypes)
  Hamartia hardcoded as "Unformed" — Lachesis overwrites at Turn 10.
-->
<script lang="ts">
	import { get } from 'svelte/store';
	import { vestibuleState, playerId } from '$lib/stores/vestibule';
	import { initGame } from '$lib/stores/engine';

	let step = $state<0 | 1 | 2>(0);
	let playerName = $state('');
	let playerGender = $state('');
	let firstMemory = $state('');
	let loading = $state(false);
	let fading = $state(false);
	let error = $state('');

	const MEMORIES = [
		'A light in the distance I could not reach.',
		'The weight of a heavy stone in my hand.',
		'A crowd shouting a name that was not mine.',
		'A cold shadow that moved when I moved.',
	];

	function handleNameSubmit(e: KeyboardEvent) {
		if (e.key !== 'Enter') return;

		const trimmed = playerName.trim();
		if (!trimmed) {
			error = 'The void demands a name.';
			return;
		}
		if (trimmed.length > 30) {
			error = 'Even the gods cannot hold so many syllables.';
			return;
		}

		error = '';
		playerName = trimmed;
		step = 1;
	}

	function selectGender(gender: string) {
		playerGender = gender;
		step = 2;
	}

	async function selectMemory(memory: string) {
		firstMemory = memory;
		fading = true;

		// Wait for fade-out animation (2s)
		await new Promise((resolve) => setTimeout(resolve, 2000));

		loading = true;
		try {
			await initGame({
				player_id: get(playerId),
				name: playerName,
				gender: playerGender,
				hamartia: 'Unformed',
				first_memory: firstMemory,
			});
			vestibuleState.set('playing');
		} catch (err) {
			// On failure, undo fade and show error
			fading = false;
			loading = false;
			error = 'The Loom falters. Try again.';
		}
	}
</script>

<div class="incarnation-screen" class:incarnation-fade-out={fading}>
	{#if step === 0}
		<!-- Step 0: Name -->
		<div class="step-enter">
			<p class="incarnation-prose">
				A thread stirs in the void. Before the Fates can weave,<br />
				they must know the shape of the soul.
			</p>
			<p class="incarnation-prompt">What name does this soul carry?</p>
			<input
				class="incarnation-input"
				type="text"
				placeholder="Speak your name..."
				bind:value={playerName}
				onkeydown={handleNameSubmit}
				maxlength={30}
				autofocus
			/>
			{#if error}
				<p class="incarnation-error step-enter">{error}</p>
			{/if}
		</div>
	{:else if step === 1}
		<!-- Step 1: Gender -->
		<div class="step-enter">
			<p class="incarnation-prose">
				The thread takes form. <em>{playerName}</em>...<br />
				the Fates taste the syllables.
			</p>
			<p class="incarnation-prompt">What shape does this soul wear?</p>
			<div class="gender-buttons fade-in">
				<button
					class="nyx-choice-btn phase-3"
					onclick={() => selectGender('boy')}
				>
					A Boy
				</button>
				<button
					class="nyx-choice-btn phase-3"
					onclick={() => selectGender('girl')}
				>
					A Girl
				</button>
			</div>
			{#if error}
				<p class="incarnation-error step-enter">{error}</p>
			{/if}
		</div>
	{:else}
		<!-- Step 2: First Memory -->
		<div class="step-enter">
			<p class="incarnation-prose">
				The thread is woven. But where does it fall?
			</p>
			<p class="incarnation-prompt">What is your earliest memory?</p>
			<div class="memory-buttons fade-in">
				{#each MEMORIES as memory}
					<button
						class="nyx-choice-btn phase-3"
						onclick={() => selectMemory(memory)}
						disabled={loading}
					>
						{memory}
					</button>
				{/each}
			</div>
			{#if error}
				<p class="incarnation-error step-enter">{error}</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.incarnation-prose {
		font-family: var(--font-prose);
		font-size: 1.2rem;
		color: var(--nyx-text-dim);
		line-height: 1.85;
		text-align: center;
		margin: 0 0 2rem 0;
	}

	.incarnation-prompt {
		font-family: var(--font-prose);
		font-style: italic;
		font-size: 1.1rem;
		color: var(--nyx-text);
		text-align: center;
		margin: 0 0 1.5rem 0;
	}

	.incarnation-input {
		display: block;
		margin: 0 auto;
		width: 280px;
		padding: 0.5rem 0;
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--nyx-border);
		color: var(--nyx-text);
		font-family: var(--font-prose);
		font-size: 1.1rem;
		text-align: center;
		outline: none;
		transition: border-color 300ms ease;
	}

	.incarnation-input::placeholder {
		color: var(--nyx-text-dim);
		opacity: 0.5;
	}

	.incarnation-input:focus {
		border-bottom-color: var(--nyx-oracle-gold);
	}

	.incarnation-error {
		font-family: var(--font-prose);
		font-style: italic;
		font-size: 0.85rem;
		color: var(--nyx-nemesis);
		text-align: center;
		margin: 1rem 0 0 0;
		opacity: 0.8;
	}

	.gender-buttons {
		display: flex;
		gap: 2rem;
		justify-content: center;
		margin-top: 2rem;
	}

	.memory-buttons {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		align-items: center;
		margin-top: 2rem;
		max-width: 460px;
		margin-left: auto;
		margin-right: auto;
	}
</style>
