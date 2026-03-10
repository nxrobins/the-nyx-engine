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

					return `<p>${line}</p>`;
				})
				.filter(Boolean)
				.join('');
		})
		.join('<hr class="nyx-divider">');
}
