import { formPoints, pickSort, sortRows, type Cols, type TableRow } from '#lib/league.ts';
import { leagueBase } from '#lib/server/league.ts';

// This season's actual table, one per group, zones coloured from the feed's notes
export async function load({ fetch, params, url, locals }) {
	const { table, club, zones, byTeam } = await leagueBase(fetch, params.id, locals.token);
	type Row = TableRow & { name: string; current: number | null };
	const rows: Row[] = table.map((r) => ({ ...r, name: club(r.team), current: byTeam.get(r.team)?.current ?? null }));
	const cols: Cols<Row> = {
		rank: { dir: 1, val: (r) => r.rank }, club: { dir: 1, val: (r) => r.name },
		played: { dir: -1, val: (r) => r.played }, win: { dir: -1, val: (r) => r.win }, draw: { dir: -1, val: (r) => r.draw },
		lose: { dir: -1, val: (r) => r.lose }, gf: { dir: -1, val: (r) => r.gf }, ga: { dir: 1, val: (r) => r.ga },
		gd: { dir: -1, val: (r) => r.gd }, points: { dir: -1, val: (r) => r.points },
		xg90: { dir: -1, val: (r) => r.xg90 }, xga90: { dir: 1, val: (r) => r.xga90 },
		form: { dir: -1, val: (r) => formPoints(r.form) }, current: { dir: -1, val: (r) => r.current }
	};
	const hasXg = rows.some((r) => r.xg90 != null); // leagues without shot data don't get the columns
	const asked = url.searchParams.get('sort');
	const sort = pickSort(cols, 'rank', !hasXg && asked?.startsWith('xg') ? null : asked, url.searchParams.has('rev'));
	const groups = [...new Set(rows.map((r) => r.group))];
	return {
		sort, hasXg, several: groups.length > 1,
		groups: groups.map((g) => ({ name: g ?? '', rows: sortRows(rows.filter((r) => r.group === g), sort, cols).map((r) => ({ ...r, zone: (r.description && zones.get(r.description)) || '' })) })),
		legend: [...zones].map(([text, cls]) => ({ text, cls }))
	};
}
