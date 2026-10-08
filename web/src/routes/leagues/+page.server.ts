import { countryDisplay } from '#lib/clubTable.ts';
import { leagueAverages } from '#lib/league.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { clubs, tiers, type RankingsDoc } from '#lib/rankings.ts';
import { keptDoc } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import type { Site } from '#lib/site.ts';

const SORTS = ['clubs', 'lt', 'trend', 'current'] as const;

// Every league with rated clubs, laid out like the Clubs ranking: strongest first by the average
// Baseline Strength of its clubs (the number on each league's page), or by another column
export async function load({ fetch, url, locals, setHeaders }) {
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings')]);
	const all = clubs(doc);
	const asked = url.searchParams.get('sort') as (typeof SORTS)[number];
	const sort = SORTS.includes(asked) ? asked : 'lt';
	const ltTier = tiers(all, 'lt'), currentTier = tiers(all, 'current');
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	return {
		sort, tabHead: { title: 'Leagues', ...TAB_INFO.leagues },
		leagues: leagueAverages(site, all).sort((a, b) => b[sort] - a[sort] || b.lt - a.lt).map((c) => {
			const country = countryDisplay(c.country);
			return { lid: c.lid, name: c.name, countryKey: c.country, country, hasFlag: !!FLAG_CODES[country], clubs: c.clubs,
				lt: Math.round(c.lt), ltTier: ltTier(c.lt), trend: c.trend, current: Math.round(c.current), currentTier: currentTier(c.current) };
		})
	};
}
