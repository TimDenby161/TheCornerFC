// What a link to a page shows where it's shared (X, WhatsApp, Facebook, Slack) and which address
// search engines take as the page's own (task T-031). Every page already writes its <title> and
// description in its own <svelte:head>; this copies them into the share tags as the page is sent,
// so no page has to say them twice.
//   og:* / twitter:*   title, description, the page's address and the site's card image
//   canonical          the page's address without its query (/clubs?sort=st is /clubs)
export const SHARE_IMAGE = '/share-card.png';
export const X_ACCOUNT = '@TheCorner_FC';

const SITE = ' · The Corner FC';
const unescape = (s: string) => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const escape = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function shareTags(html: string, origin: string, path: string): string {
	const end = html.indexOf('</head>');
	if (end < 0 || html.includes('property="og:title"')) return html;
	const head = html.slice(0, end);
	const title = unescape(head.match(/<title>([^<]*)<\/title>/)?.[1] ?? 'The Corner FC');
	const description = unescape(head.match(/<meta name="description" content="([^"]*)"/)?.[1] ?? '');
	const url = origin + path;
	const tags = [
		['link', 'canonical', url],
		['og:type', 'website'], ['og:site_name', 'The Corner FC'],
		// on a card the site's name is already shown, so the title loses its " · The Corner FC"
		['og:title', title.endsWith(SITE) ? title.slice(0, -SITE.length) : title],
		...(description ? [['og:description', description]] : []),
		['og:url', url], ['og:image', origin + SHARE_IMAGE], ['og:image:width', '1200'], ['og:image:height', '630'],
		['twitter:card', 'summary_large_image'], ['twitter:site', X_ACCOUNT]
	].map(([name, a, b]) => name === 'link' ? `<link rel="canonical" href="${escape(b)}" />`
		: name.startsWith('og:') ? `<meta property="${name}" content="${escape(a)}" />`
		: `<meta name="${name}" content="${escape(a)}" />`);
	return head + tags.join('') + html.slice(end);
}
