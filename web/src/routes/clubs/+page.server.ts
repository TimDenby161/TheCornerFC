import { TAB_INFO } from '#lib/tabInfo.ts';
import { keptDoc } from '#lib/server/database.ts';
import { loadCups } from '#lib/server/cups.ts';
import { CLUB_TITLES, clubCounts, countryDisplay, filterMenu, isExcludeKey, knownFilter, tableCountries, tableRows } from '#lib/clubTable.ts';
import { CLUB_SHORT } from '#lib/names.ts';
import { clubPlaces, clubs, SORTS, tiers, type RankingsDoc, type Sort } from '#lib/rankings.ts';
import { leagueShort, teamName, type Site } from '#lib/site.ts';

export async function load({ fetch, url, setHeaders, locals }) {
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
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });

	return {
		sort, filter, search, wide, menu,
		excluded: [...excluded],
		tabHead: { title: 'Clubs', ...TAB_INFO.clubs },
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
