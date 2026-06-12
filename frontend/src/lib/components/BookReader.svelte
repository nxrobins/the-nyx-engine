<!--
  The Book Reader — a bound life, opened.
  Shared by the Death Rite (your own book) and the Library (the shelf).
  Full-screen overlay; renders the bookbinder's markdown.
-->
<script lang="ts">
	import { fade } from 'svelte/transition';
	import { fetchBookMarkdown } from '$lib/stores/library';
	import { renderBook } from '$lib/utils/markdown';

	let { bookId, onClose }: { bookId: string; onClose: () => void } = $props();

	let markdown = $state<string | null>(null);
	let failed = $state(false);

	$effect(() => {
		markdown = null;
		failed = false;
		fetchBookMarkdown(bookId).then((md) => {
			if (md === null) failed = true;
			else markdown = md;
		});
	});
</script>

<div class="book-reader-overlay" transition:fade={{ duration: 500 }}>
	<div class="book-reader-scroll">
		<div class="book-reader-page">
			{#if failed}
				<p class="book-reader-empty">
					The shelf holds the spine, but the pages will not open.
				</p>
			{:else if markdown === null}
				<p class="book-reader-empty">The pages turn themselves open...</p>
			{:else}
				<article class="book-body">
					{@html renderBook(markdown)}
				</article>
			{/if}

			<div class="book-reader-close-row">
				<button class="book-reader-close" onclick={onClose}>
					[ Close the Book ]
				</button>
			</div>
		</div>
	</div>
</div>
