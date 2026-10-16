import { error } from '@sveltejs/kit';
import { SITE_ENV, SITE_HOST } from '#lib/config.ts';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { keptDoc } from '#lib/server/database.ts';
import { sitemap } from '#lib/sitemap.ts';

// The live site's sitemap (lib/sitemap.ts). Anywhere else there is none: staging and any other
// address are kept out of search engines (robots.txt).
export async function GET({ fetch, url }) {
	if (SITE_ENV !== 'production' || url.hostname !== SITE_HOST) error(404, 'Not found');
	const doc = await keptDoc<RankingsDoc>(fetch, 'rankings');
	return new Response(sitemap(`https://${SITE_HOST}`, clubs(doc)), {
		headers: { 'content-type': 'application/xml; charset=utf-8', 'cache-control': 'public, max-age=86400' }
	});
}
