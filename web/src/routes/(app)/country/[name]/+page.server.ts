import { error } from '@sveltejs/kit';
import { countryDisplay } from '#lib/clubTable.ts';
import { avgRating, leagueClubs, pickSort, sortRows } from '#lib/league.ts';
import { GROUP_ORDER } from '#lib/matchday.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { clubs, tiers, type RankingsDoc } from '#lib/rankings.ts';
import { keptDoc } from '#lib/server/database.ts';
import { ratingRows, STRENGTH_COLS } from '#lib/server/league.ts';
import { leagueShort, teamName, type Site } from '#lib/site.ts';

const LIMIT = 50;

// A country: its leagues (strongest first), cups and clubs
export async function load({ fetch, params, url, locals, setHeaders }) {
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings')]);
	const country = params.name;
	const comps = Object.entries(site.competitions).filter(([, c]) => c.country === country && c.type !== 'International').map(([lid, c]) => ({ lid: Number(lid), ...c }));
	if (!comps.length) error(404, 'Not found');
	const all = clubs(doc), name = countryDisplay(country), tier = tiers(all, 'lt');
	const leagues = comps.filter((c) => c.type === 'League').map((c) => { const list = leagueClubs(all, c.lid); return { ...c, list, avg: avgRating(list) }; })
		.sort((a, b) => (b.avg ?? -1) - (a.avg ?? -1));
	const order = (lid: number) => { const k = GROUP_ORDER.indexOf(lid); return k < 0 ? 999 : k; };
	const cups = comps.filter((c) => c.type !== 'League').sort((a, b) => order(a.lid) - order(b.lid));
	const list = leagues.flatMap((c) => c.list).sort((a, b) => b.lt - a.lt);
	const avg = avgRating(list.slice(0, 15)); // the country's level: its 15 best clubs
	// sorted by Current Strength to start; # stays the Baseline Strength rank
	const sort = pickSort(STRENGTH_COLS, 'current', url.searchParams.get('sort'), url.searchParams.has('rev'));
	const showAll = url.searchParams.get('all') === '1';
	const rows = sortRows(ratingRows(all, (t) => teamName(site, t))(list, null, leagues.length > 1 ? (r) => ({ league: r.league, name: leagueShort(site, r.league) }) : null), sort, STRENGTH_COLS);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const card = (c: { lid: number; name: string; list?: typeof list; avg?: number | null }) => ({
		lid: c.lid, name: c.name, sub: c.list?.length ? `${c.list.length} clubs · top rated ${teamName(site, c.list[0].team)}` : '',
		avg: c.avg != null ? { value: Math.round(c.avg), tier: tier(c.avg) } : null
	});
	return {
		name, flag: FLAG_CODES[name] ?? null, sort, showAll, total: list.length,
		counts: [[leagues.length, 'league'], [cups.length, 'cup'], [list.length, 'club']].filter(([n]) => n).map(([n, word]) => `${n} ${word}${n === 1 ? '' : 's'}`).join(' · '),
		avg: avg == null ? null : { value: Math.round(avg), tier: tier(avg) },
		leagues: leagues.map(card), cups: cups.map(card),
		rows: showAll ? rows : rows.slice(0, LIMIT)
	};
}
