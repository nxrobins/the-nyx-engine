/**
 * The Library — bound lives from the Tapestry's shelf (Scribe P3).
 *
 * Thin fetchers over GET /library and GET /library/{book_id}.
 * Silent-fail posture matches vestibule.fetchPastThreads: an empty
 * shelf renders fine; a missing book shows the reader's empty state.
 */

import { writable } from 'svelte/store';
import type { LibraryBook } from '$lib/types/engine';

export const libraryBooks = writable<LibraryBook[]>([]);

export async function fetchLibrary(): Promise<void> {
	try {
		const res = await fetch('/api/library');
		if (!res.ok) return;
		const data = await res.json();
		libraryBooks.set(data.books || []);
	} catch {
		// Silent fail — an empty shelf is fine
	}
}

export async function fetchBookMarkdown(bookId: string): Promise<string | null> {
	try {
		const res = await fetch(`/api/library/${encodeURIComponent(bookId)}`);
		if (!res.ok) return null;
		const data = await res.json();
		return data.markdown ?? null;
	} catch {
		return null;
	}
}
