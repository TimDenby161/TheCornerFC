import { headline, projectable } from '#lib/league.ts';
import { leagueBase } from '#lib/server/league.ts';

// The projected table. The whole of it (the rest of the season played out from the model's
// predictions) is for subscribers; anyone else gets the headline the database sends: where the
// model expects each club to finish, and on how many points.
export async function load({ fetch, params, locals }) {
	const { lg, table, fixtures, club, zones } = await leagueBase(fetch, params.id, locals.token);
	const legend = [...zones].map(([text, cls]) => ({ text, cls }));
	const groups = [...new Set(table.map((r) => r.group))];
	// the zone a place carries today, by group
	const zoneOf = (g: string | null, place: number) => { const d = table.find((r) => r.group === g && r.rank === place)?.description; return (d && zones.get(d)) || ''; };
	const names = Object.fromEntries(table.map((r) => [r.team, club(r.team)]));
	if (lg?.cut) {
		const list = headline(lg);
		return {
			mode: 'headline' as const, legend, several: groups.length > 1,
			groups: [...new Set(list.map((x) => x.group))].map((g) => ({ name: g ?? '', rows: list.filter((x) => x.group === g).map((x) => ({ ...x, name: club(x.team), zone: zoneOf(g, x.place) })) }))
		};
	}
	const upcoming = projectable(fixtures);
	return {
		mode: 'full' as const, legend, several: groups.length > 1, names, left: upcoming.length,
		// what the page plays the season out from: each group's table so far, and the fixtures left
		groups: groups.map((g) => {
			const rows = table.filter((r) => r.group === g);
			return {
				name: g ?? '', rows, zones: rows.map((r) => zoneOf(g, r.rank)),
				// a zone's chance is the chance of finishing in any of the places carrying its note today
				cols: legend.filter((z) => rows.some((r) => r.description === z.text)).map((z) => ({ ...z, places: rows.filter((r) => r.description === z.text).map((r) => r.rank - 1) }))
			};
		}),
		fixtures: upcoming.map((f) => ({ id: f.id, kickoff: f.kickoff, round: f.round, status: f.status, home: f.home, away: f.away, hg: null, ag: null, pen_h: null, pen_a: null,
			home_xg: f.home_xg, away_xg: f.away_xg, p_home: f.p_home, p_draw: f.p_draw, p_away: f.p_away }))
	};
}
