import { SITE_HOST } from '#lib/config.ts';

// Search engines are let in at the site's own address only. Anywhere else this app answers (the
// workers.dev preview address) is the same pages twice over, so they are kept out there. The
// account, the owner's fantasy pages and the server's own addresses are never for them.
export function GET({ url }) {
	const body = url.hostname === SITE_HOST
		? ['User-agent: *', 'Disallow: /account', 'Disallow: /fantasy/', 'Disallow: /fpl', 'Disallow: /my-fpl-team', 'Disallow: /efl-fantasy', 'Disallow: /stripe/', 'Disallow: /players/rows', 'Disallow: /players/options', 'Disallow: /players/seasons', '']
		: ['User-agent: *', 'Disallow: /', ''];
	return new Response(body.join('\n'), { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' } });
}
