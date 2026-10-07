import { keptDoc } from '#lib/server/database.ts';
import { clubPlaces, clubRows, clubs, SORTS, tiers, type RankingsDoc, type Sort } from '#lib/rankings.ts';
import { countryName, leagueShort, teamName, type Site } from '#lib/site.ts';

const PER_PAGE = 100;

export async function load({ fetch, url, setHeaders }) {
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings')]);
	const all = clubs(doc);

	const asked = url.searchParams.get('sort') as Sort;
	const sort: Sort = SORTS.includes(asked) ? asked : 'lt';
	const c = url.searchParams.get('c') ?? '';
	const league = /^\d+$/.test(c) && site.competitions[c] ? Number(c) : null;
	const rows = clubRows(all, sort, league);
	const pages = Math.max(1, Math.ceil(rows.length / PER_PAGE));
	const pageNo = Math.min(pages, Math.max(1, Number(url.searchParams.get('page')) || 1));

	const places = clubPlaces(all);
	const baseTier = tiers(all, 'lt'), currentTier = tiers(all, 'current');
	// the same answer for every visitor: a shared cache may keep it for a minute
	setHeaders({ 'cache-control': 'public, max-age=60' });

	return {
		sort, league, pageNo, pages, total: rows.length,
		leagueName: league === null ? null : leagueShort(site, league),
		rows: rows.slice((pageNo - 1) * PER_PAGE, pageNo * PER_PAGE).map((r, i) => {
			const comp = site.competitions[r.league];
			return {
				n: (pageNo - 1) * PER_PAGE + i + 1,
				team: r.team,
				name: teamName(site, r.team),
				league: r.league,
				leagueName: leagueShort(site, r.league),
				country: comp ? countryName(comp) : '',
				place: places.get(r.team)!,
				lt: Math.round(r.lt), ltTier: baseTier(r.lt),
				current: Math.round(r.current), currentTier: currentTier(r.current),
				trend: r.trend,
				form: r.form == null ? null : Math.round(r.form)
			};
		})
	};
}
