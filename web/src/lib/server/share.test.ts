import { describe, expect, it } from 'vitest';
import { SHARE_IMAGE, shareTags } from './share';

const page = (head: string) => `<!doctype html><html><head><meta charset="utf-8" />${head}</head><body><p>hi</p></body></html>`;
const tag = (html: string, name: string) => html.match(new RegExp(`<meta (?:property|name)="${name}" content="([^"]*)"`))?.[1];

describe('share tags', () => {
	it("copy the page's own title and description, and point at its address and the card", () => {
		const html = shareTags(page('<title>Arsenal · The Corner FC</title><meta name="description" content="Arsenal: strength rating &amp; form." />'), 'https://thecornerfc.com', '/club/42');
		expect(tag(html, 'og:title')).toBe('Arsenal');
		expect(tag(html, 'og:description')).toBe('Arsenal: strength rating &amp; form.');
		expect(tag(html, 'og:url')).toBe('https://thecornerfc.com/club/42');
		expect(tag(html, 'og:image')).toBe('https://thecornerfc.com' + SHARE_IMAGE);
		expect(tag(html, 'twitter:card')).toBe('summary_large_image');
		expect(tag(html, 'twitter:site')).toBe('@TheCorner_FC');
		expect(html).toContain('<link rel="canonical" href="https://thecornerfc.com/club/42" />');
		expect(html.indexOf('og:title')).toBeLessThan(html.indexOf('</head>'));
		expect(html).toContain('<body><p>hi</p></body>');
	});
	it('keep the whole title when it is the site itself, and leave out a missing description', () => {
		const html = shareTags(page('<title>The Corner FC</title>'), 'https://thecornerfc.com', '/');
		expect(tag(html, 'og:title')).toBe('The Corner FC');
		expect(tag(html, 'og:description')).toBeUndefined();
	});
	it('escape what they copy, so a quote in a name cannot break out of the tag', () => {
		const html = shareTags(page('<title>N&#39;Golo &quot;K&quot; · The Corner FC</title>'), 'https://thecornerfc.com', '/player/1');
		expect(tag(html, 'og:title')).toBe('N\'Golo &quot;K&quot;');
		expect(html).not.toContain('content="N\'Golo "K"');
	});
	it('leave a page alone that has no head, or already has its own', () => {
		expect(shareTags('<p>partial chunk</p>', 'https://x', '/')).toBe('<p>partial chunk</p>');
		const own = page('<meta property="og:title" content="Mine" />');
		expect(shareTags(own, 'https://x', '/')).toBe(own);
	});
});
