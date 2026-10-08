// The plain text pages (terms, privacy, how the models work) are still the old site's own files in
// docs/, read from where they are until the domain moves to this app, so the wording can't drift
// between the two. This takes one's text out of its file and points its links at this site.
export function textPage(html: string) {
	const main = /<main>([\s\S]*)<\/main>/.exec(html)?.[1] ?? '';
	return {
		title: /<title>([^<]*)<\/title>/.exec(html)?.[1] ?? 'The Corner FC',
		description: /<meta name="description" content="([^"]*)"/.exec(html)?.[1] ?? '',
		html: main
			.replace(/href="\.\/#\/([\w-]+)"/g, 'href="/$1"')                              // a section of the site
			.replace(/href="(terms|privacy|methodology)\.html(#[\w-]+)?"/g, (_, p, hash) => `href="/${p}${hash ?? ''}"`)
			.replace(/href="\.\/"/g, 'href="/"')
			.replace(/href="\.well-known\//g, 'href="/.well-known/')
	};
}
// the same, cut where the page has a box for live figures (<div id="..-live" ...>...</div>): the
// text before each box with the box's id, then the rest
export function textParts(html: string): { html: string; live: string | null }[] {
	const parts: { html: string; live: string | null }[] = [];
	let rest = html;
	for (;;) {
		const m = /<div id="([\w-]+-live)"[^>]*>[\s\S]*?<\/div>/.exec(rest);
		if (!m) break;
		parts.push({ html: rest.slice(0, m.index), live: m[1] });
		rest = rest.slice(m.index + m[0].length);
	}
	parts.push({ html: rest, live: null });
	return parts;
}
