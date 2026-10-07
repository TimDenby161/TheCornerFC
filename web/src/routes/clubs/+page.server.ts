import { keptDoc } from '#lib/server/database.ts';
import { loadCups } from '#lib/server/cups.ts';
import { CLUB_TITLES, clubCounts, countryDisplay, filterMenu, isExcludeKey, knownFilter, tableCountries, tableRows } from '#lib/clubTable.ts';
import { CLUB_SHORT } from '#lib/names.ts';
import { clubPlaces, clubs, SORTS, tiers, type RankingsDoc, type Sort } from '#lib/rankings.ts';
import { leagueShort, teamName, type Site } from '#lib/site.ts';

export async function load({ fetch, url, setHeaders }) {
	const [site, doc, cups] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings'), loadCups(fetch)]);
	const all = clubs(doc);
	const countries = tableCountries(site, all);

	const q = url.searchParams;
	const asked = q.get('sort') as Sort;
	const sort: Sort = SORTS.includes(asked) ? asked : 'lt';
	const filter = knownFilter(q.get('c'), site, countries) ? q.get('c')! : 'all';
	const excluded = new Set((q.get('ex') || '').split('|').filter(isExcludeKey));
	const search = (q.get('q') || '').slice(0, 80);

	const { rows, wide } = tableRows(site, all, countries, cups, { filter, excluded, search, sort });
	const menu = filterMenu(site, countries, filter, clubCounts(site, all, countries, cups, excluded), CLUB_TITLES);
	const places = clubPlaces(all);
	const baseTier = tiers(all, 'lt'), currentTier = tiers(all, 'current');
	// the same answer for every visitor: a shared cache may keep it for a minute
	setHeaders({ 'cache-control': 'public, max-age=60' });

	return {
		sort, filter, search, wide, menu,
		excluded: [...excluded],
		tabHead: {
			title: 'Clubs',
			intro: 'Every club ranked by strength, on a scale where 100 points is worth about a goal a game.',
			more: 'terms',
			key: [
				['Baseline (Base)', "A club's long-term level: its rating averaged over roughly its last 100 matches. Slow to move."],
				['Current', 'Its rating after its latest match. It rises when the club does better than expected, and falls when it does worse.'],
				['Gap', 'Current minus Baseline. Green: playing above its usual level. Red: below it.'],
				['Last 6', 'How far its rating has moved over its last 6 matches.'],
				['World', 'Its place among every ranked club, by Baseline.'],
				['In lg', "Its place among the clubs in its own league, by Baseline. This is the site's ranking, not the league table."]
			]
		},
		rows: rows.map((r) => {
			const comp = site.competitions[r.league];
			return {
				team: r.team,
				name: teamName(site, r.team),
				short: CLUB_SHORT[r.team],
				league: r.league,
				leagueName: leagueShort(site, r.league),
				countryKey: comp?.country ?? '',
				country: comp ? countryDisplay(comp.country) : '',
				place: places.get(r.team)!,
				lt: Math.round(r.lt), ltTier: baseTier(r.lt),
				current: Math.round(r.current), currentTier: currentTier(r.current),
				trend: r.trend,
				form: r.form == null ? null : Math.round(r.form)
			};
		})
	};
}
