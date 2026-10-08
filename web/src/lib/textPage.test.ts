import { describe, expect, it } from 'vitest';
import { textPage, textParts } from './textPage';

const file = `<!doctype html><html><head><title>Terms of use · The Corner FC</title>
<meta name="description" content="The terms for using The Corner FC.">
<link rel="stylesheet" href="assets/page.css"></head><body><main>
<p class="back"><a href="./">The Corner FC</a></p><h1>Terms</h1>
<p>See <a href="privacy.html#corrections">report an error</a>, <a href="methodology.html">how it works</a>, the <a href="./#/lineups">line-up record</a>
and <a href=".well-known/security.txt">security.txt</a>, or <a href="https://example.org/terms.html">elsewhere</a>.</p>
<div id="fresh-live" class="live" aria-live="polite"><p class="muted">Loading…</p></div>
<h2 id="more">More</h2><div id="version-live" class="live"><p>Loading…</p></div><p>The end.</p>
</main><script src="assets/data.js"></script></body></html>`;

describe('textPage', () => {
	const page = textPage(file);
	it('takes the title, the description and the text, and nothing outside it', () => {
		expect(page.title).toBe('Terms of use · The Corner FC');
		expect(page.description).toBe('The terms for using The Corner FC.');
		expect(page.html).toContain('<h1>Terms</h1>');
		expect(page.html).not.toContain('<script');
		expect(page.html).not.toContain('page.css');
	});
	it('points the old site\'s links at this one, and leaves other sites\' alone', () => {
		expect(page.html).toContain('href="/privacy#corrections"');
		expect(page.html).toContain('href="/methodology"');
		expect(page.html).toContain('href="/lineups"');
		expect(page.html).toContain('href="/"');
		expect(page.html).toContain('href="/.well-known/security.txt"');
		expect(page.html).toContain('href="https://example.org/terms.html"');
	});
	it('cuts the text at each box of live figures', () => {
		const parts = textParts(page.html);
		expect(parts.map((p) => p.live)).toEqual(['fresh-live', 'version-live', null]);
		expect(parts[1].html).toContain('<h2 id="more">More</h2>');
		expect(parts[2].html).toContain('The end.');
		expect(parts.map((p) => p.html).join('')).not.toContain('Loading…');
	});
});
