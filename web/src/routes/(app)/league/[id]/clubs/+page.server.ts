import { leagueRanked, pickSort, sortRows } from '#lib/league.ts';
import { leagueBase, ratingRows, STRENGTH_COLS } from '#lib/server/league.ts';

// The competition's clubs by Baseline Strength, with their actual table position
export async function load({ fetch, params, url, locals }) {
	const { id, all, table, fixtures, club } = await leagueBase(fetch, params.id, locals.token);
	const pos = new Map(table.map((r) => [r.team, r.rank]));
	const sort = pickSort(STRENGTH_COLS, 'lt', url.searchParams.get('sort'), url.searchParams.has('rev'));
	const rows = ratingRows(all, club)(leagueRanked(all, id, table, fixtures), table.length ? (r) => pos.get(r.team) ?? null : null);
	return { sort, hasTable: table.length > 0, rows: sortRows(rows, sort, STRENGTH_COLS) };
}
