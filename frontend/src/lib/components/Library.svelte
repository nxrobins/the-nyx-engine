<!--
  The Library of Severed Threads — the Tapestry as an actual shelf.
  Lists bound lives (Scribe P3); a spine opens the Book Reader.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import { libraryBooks } from '$lib/stores/library';
	import BookReader from './BookReader.svelte';

	let { onClose }: { onClose: () => void } = $props();

	let openBookId = $state<string | null>(null);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="library-overlay"
	transition:fade={{ duration: 500 }}
	onclick={(e) => e.stopPropagation()}
>
	<div class="library-frame">
		<p class="library-title">THE LIBRARY OF SEVERED THREADS</p>
		<p class="library-subtitle">Every bound life. The dead, on their shelf.</p>

		<div class="library-shelf">
			{#if $libraryBooks.length === 0}
				<p class="library-empty">
					The shelf stands empty. No life has yet been lived long enough to bind.
				</p>
			{:else}
				{#each $libraryBooks as book}
					<button class="library-spine" onclick={() => (openBookId = book.book_id)}>
						<span class="library-spine-title">{book.title}</span>
						<span class="library-spine-meta">
							{book.hamartia || 'No flaw recorded'}
							· fell at turn {book.died_turn}
							· {book.chapter_count} chapter{book.chapter_count === 1 ? '' : 's'}
						</span>
						<span class="library-spine-epitaph">"{book.epitaph}"</span>
					</button>
				{/each}
			{/if}
		</div>

		<button class="library-close" onclick={onClose}>[ Leave the Library ]</button>
	</div>
</div>

{#if openBookId}
	<BookReader bookId={openBookId} onClose={() => (openBookId = null)} />
{/if}
