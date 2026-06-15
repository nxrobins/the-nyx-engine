import { describe, it, expect } from 'vitest';
import { renderBook, renderProse } from './markdown';

describe('renderBook', () => {
	it('returns empty string for empty input', () => {
		expect(renderBook('')).toBe('');
	});

	it('renders the bookbinder dialect headings, epitaph, and divider', () => {
		expect(renderBook('# The Hubris of Vesna')).toBe(
			'<h1 class="book-title">The Hubris of Vesna</h1>'
		);
		expect(renderBook('## Chapter One')).toBe('<h2 class="book-chapter">Chapter One</h2>');
		expect(renderBook('> Here lies one who reached too far.')).toBe(
			'<blockquote class="book-epitaph">Here lies one who reached too far.</blockquote>'
		);
		expect(renderBook('---')).toBe('<hr class="nyx-divider">');
	});

	it('renders bold and italic inline', () => {
		expect(renderBook('a **bold** and *soft* line')).toBe(
			'<p>a <strong>bold</strong> and <em>soft</em> line</p>'
		);
	});

	it('groups consecutive lines into one paragraph, split on blank lines', () => {
		expect(renderBook('line one\nline two\n\nlater')).toBe(
			'<p>line one line two</p><p>later</p>'
		);
	});

	it('escapes HTML so book prose can never inject markup (XSS guard)', () => {
		const html = renderBook('a <script>alert(1)</script> & <b>tag</b>');
		expect(html).not.toContain('<script>');
		expect(html).toContain('&lt;script&gt;');
		expect(html).toContain('&amp;');
	});
});

describe('renderProse', () => {
	it('returns empty string for empty input', () => {
		expect(renderProse('')).toBe('');
	});

	it('wraps paragraphs and converts single newlines to <br>', () => {
		expect(renderProse('one\n\ntwo')).toBe('<p>one</p><p>two</p>');
		expect(renderProse('a\nb')).toBe('<p>a<br>b</p>');
	});

	it('splits on --- into hr-joined sections', () => {
		expect(renderProse('before\n---\nafter')).toBe(
			'<p>before</p><hr class="nyx-divider"><p>after</p>'
		);
	});

	it('renders bold/italic and escapes stray HTML', () => {
		expect(renderProse('**hit** then *fade*')).toBe(
			'<p><strong>hit</strong> then <em>fade</em></p>'
		);
		expect(renderProse('5 < 6 & 7 > 2')).toContain('&lt;');
		expect(renderProse('<img src=x onerror=1>')).not.toContain('<img');
	});
});
