import { countryDisplay } from '#lib/clubTable.ts';
import { avgRating, leagueClubs } from '#lib/league.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { tiers } from '#lib/rankings.ts';
import { leagueBase } from '#lib/server/league.ts';
import { compLabel } from '#lib/site.ts';

export async function load({ fetch, params, locals, setHeaders }) {
	const { id, site, all, lg, comp, table } = await leagueBase(fetch, params.id, locals.token);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const avg = avgRating(leagueClubs(all, id));
	const country = countryDisplay(comp?.country ?? 'World');
	return {
		id, name: comp?.name ?? compLabel(site, id), label: compLabel(site, id),
		countryKey: comp?.country ?? 'World', country, flag: FLAG_CODES[country] ?? null,
		avg: avg == null ? null : { value: Math.round(avg), tier: tiers(all, 'lt')(avg) },
		hasData: !!lg,
		// a cup without a table has no standings and nothing to project
		tabs: ([['table', 'Standings'], ['clubs', 'Strength ranking'], ['projected', 'Projected table'], ['matches', 'Matches']] as [string, string][])
			.filter(([k]) => (k !== 'table' && k !== 'projected') || table.length > 0)
	};
}
