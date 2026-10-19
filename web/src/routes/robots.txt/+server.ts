import { SITE_ENV, SITE_HOST } from '#lib/config.ts';
import { SEO_BOTS } from '#lib/robots.ts';

// Search engines are let in at the live site's own address only. Anywhere else this app answers
// (the workers.dev preview address) is the same pages twice over, and staging is not for them
// at any address, so they are kept out there. The
// account, the owner's fantasy pages and the server's own addresses are never for them. The
// sitemap (sitemap.xml) lists the main pages, leagues and clubs.
export function GET({ url }) {
	const body = SITE_ENV === 'production' && url.hostname === SITE_HOST
		? [...SEO_BOTS.flatMap((bot) => [`User-agent: ${bot}`, 'Disallow: /', '']), 'User-agent: *', 'Disallow: /account', 'Disallow: /admin', 'Disallow: /fantasy/', 'Disallow: /fpl', 'Disallow: /my-fpl-team', 'Disallow: /efl-fantasy', 'Disallow: /stripe/', 'Disallow: /players/rows', 'Disallow: /players/options', 'Disallow: /players/seasons', '', `Sitemap: https://${SITE_HOST}/sitemap.xml`, '']
		: ['User-agent: *', 'Disallow: /', ''];
	return new Response(body.join('\n'), { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' } });
}
