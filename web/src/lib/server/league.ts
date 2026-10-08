import { error } from '@sveltejs/kit';
import { leagueZones } from '#lib/club.ts';
import { fixtureRows, tableRows, type LeagueFile, type Sort } from '#lib/league.ts';
import { clubs, tiers, type Club, type RankingsDoc } from '#lib/rankings.ts';
import { teamName, type Site } from '#lib/site.ts';
import { askAs, keptDoc } from './database.ts';

// What every part of a competition's page starts from: the names, every club's ratings, and the
// competition's own file as this visitor may see it (site_league gives the whole file to a
// subscriber and a cut-down one to anyone else). A competition the names don't know, with no
// file, has no page.
export async function leagueBase(fetch: typeof globalThis.fetch, param: string, token?: string) {
	if (!/^\d{1,7}$/.test(param)) error(404, 'Not found');
	const id = Number(param);
	const [site, rankings, lg] = await Promise.all([
		keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings'),
		askAs<LeagueFile | null>(fetch, token, 'site_league', { p_id: id }).catch(() => null)
	]);
	const comp = site.competitions[id];
	if (!lg && !comp) error(404, 'Not found');
	const all = clubs(rankings);
	const table = lg ? tableRows(lg) : [], fixtures = lg ? fixtureRows(lg) : [];
	// a club's name as the competition's file has it (clubs the names row doesn't hold), else the site's
	const club = (t: number) => lg?.teams?.[t] || teamName(site, t);
	return { id, site, all, lg, comp, table, fixtures, club, zones: leagueZones(table), byTeam: new Map(all.map((c) => [c.team, c])) };
}

// A row of the clubs table on league and country pages: a club's ratings with its Baseline rank
// in the list (which stays whatever the table is sorted by)
export type RatingRow = ReturnType<ReturnType<typeof ratingRows>>[number];
export function ratingRows(all: Club[], name: (team: number) => string) {
	const ltTier = tiers(all, 'lt'), currentTier = tiers(all, 'current');
	return (rows: Club[], pos: ((r: Club) => number | null) | null = null, meta: ((r: Club) => { league: number; name: string } | null) | null = null) =>
		rows.map((r, i) => ({
			i: i + 1, team: r.team, name: name(r.team), pos: pos ? pos(r) : null, played: r.played, meta: meta ? meta(r) : null,
			lt: r.lt, ltTier: ltTier(r.lt), current: r.current, currentTier: currentTier(r.current), trend: r.trend, form: r.form
		}));
}
export const STRENGTH_COLS = {
	rank: { dir: 1 as const, val: (r: RatingRow) => r.i }, club: { dir: 1 as const, val: (r: RatingRow) => r.name }, pos: { dir: 1 as const, val: (r: RatingRow) => r.pos },
	played: { dir: -1 as const, val: (r: RatingRow) => r.played }, lt: { dir: -1 as const, val: (r: RatingRow) => r.lt }, trend: { dir: -1 as const, val: (r: RatingRow) => r.trend },
	current: { dir: -1 as const, val: (r: RatingRow) => r.current }, form: { dir: -1 as const, val: (r: RatingRow) => r.form }
};
export type { Sort };
