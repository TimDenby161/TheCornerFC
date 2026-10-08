import { json } from '@sveltejs/kit';
import { whoOptions } from '#lib/playerFilters.ts';
import { playersBase } from '#lib/server/players.ts';

// What the club and nationality boxes list, asked for when one is first opened
export async function GET({ fetch, url }) {
	const { site, facets, countries } = await playersBase(fetch, url.searchParams);
	return json(whoOptions(site, facets, countries), { headers: { 'cache-control': 'public, max-age=300' } });
}
