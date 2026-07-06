/**
 * Lightweight markdown-to-HTML renderer for Nyx prose.
 *
 * Handles only the subset used by the engine:
 *   **bold**  →  <strong>
 *   *italic*  →  <em>
 *   ---       →  <hr class="nyx-divider">
 *   \n\n      →  paragraph breaks
 *   \n        →  <br>
 */
/**
 * Render a bound life's markdown (bookbinder output) into book HTML.
 * Handles the bookbinder's exact dialect: # title, ## chapters,
 * > epitaph blockquote, --- dividers, *italic* framing lines, paragraphs.
 */
export function renderBook(raw: string): string {
	if (!raw) return '';

	const escape = (s: string) =>
		s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	const inline = (s: string) =>
		escape(s)
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.+?)\*/g, '<em>$1</em>');

	const out: string[] = [];
	let paragraph: string[] = [];
	const flush = () => {
		if (paragraph.length) {
			out.push(`<p>${inline(paragraph.join(' '))}</p>`);
			paragraph = [];
		}
	};

	for (const rawLine of raw.replace(/\r\n/g, '\n').split('\n')) {
		const line = rawLine.trim();
		if (!line) {
			flush();
		} else if (line.startsWith('## ')) {
			flush();
			out.push(`<h2 class="book-chapter">${inline(line.slice(3))}</h2>`);
		} else if (line.startsWith('# ')) {
			flush();
			out.push(`<h1 class="book-title">${inline(line.slice(2))}</h1>`);
		} else if (line.startsWith('> ')) {
			flush();
			out.push(`<blockquote class="book-epitaph">${inline(line.slice(2))}</blockquote>`);
		} else if (line === '---') {
			flush();
			out.push('<hr class="nyx-divider">');
		} else {
			paragraph.push(line);
		}
	}
	flush();
	return out.join('');
}

export function renderProse(raw: string): string {
	if (!raw) return '';

	// Normalize line endings
	let html = raw.replace(/\r\n/g, '\n');

	// Split on --- dividers first (they come as \n\n---\n\n from Nemesis/Eris postfix)
	const sections = html.split(/\n---\n/);

	return sections
		.map((section) => {
			// Split paragraphs on double newline
			const paragraphs = section.split(/\n\n+/);

			return paragraphs
				.map((p) => {
					let line = p.trim();
					if (!line) return '';

					// THE SEAL (the bow ruling): a '⁂ '-prefixed paragraph is the
					// engine-appended authored consequence — the closed box's final
					// line, rendered in its own quiet register with the seam before
					// the next card. Marker detected before escaping (engine-authored);
					// the content itself still escapes below.
					const isSeal = line.startsWith('⁂ ');
					if (isSeal) line = line.slice(2);

					// Escape any stray HTML (safety)
					line = line
						.replace(/&/g, '&amp;')
						.replace(/</g, '&lt;')
						.replace(/>/g, '&gt;');

					// **bold** → <strong> (must come before *italic*)
					line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

					// *italic* → <em>
					line = line.replace(/\*(.+?)\*/g, '<em>$1</em>');

					// Single newlines → <br>
					line = line.replace(/\n/g, '<br>');

					return isSeal
						? `<p class="vignette-seal">⁂&nbsp;${line}</p>`
						: `<p>${line}</p>`;
				})
				.filter(Boolean)
				.join('');
		})
		.join('<hr class="nyx-divider">');
}
