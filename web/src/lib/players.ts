// The Players table: what it asks the database's site_players for, and the rows that come back.
// The database filters, sorts and counts; a visitor who isn't a subscriber gets a player outside
// the free slice with his ranks blanked, in the place a subscriber would see him.
import { clubSearchText, cupTeams, filterLeagues, foldText, isCupFilter, isExcluded, type Country, type Cups } from './clubTable.ts';
import type { Club } from './rankings.ts';
import { teamName, type Site } from './site.ts';

export type Player = {
	id: number; name: string; position: string | null; rank: number | null; team: number | null; league: number | null;
	seasons: (number | null)[] | null; age: number | null; estimated: number[] | null; nationality: string | null;
	future: (number | null)[] | null; season: { minutes: number; goals: number; assists: number } | null;
	world: number | null; lg: number | null; lg_of: number | null; ord: number | null;
	// the database blanked his ranks for this visitor
	locked: boolean;
};
export type PlayersAnswer = { total: number; paywall?: boolean; rows: unknown[][]; counts?: [number, number, number][] };
export type Facets = { players: number; clubs: [number, number][] };

// API-Football sends some names HTML-encoded ("O&apos;Reilly")
const ENTITIES: Record<string, string> = { apos: "'", '#39': "'", quot: '"', amp: '&', lt: '<', gt: '>' };
export const decodeEntities = (t: string) => (t.includes('&') ? t.replace(/&(apos|#39|quot|amp|lt|gt);/g, (_, e) => ENTITIES[e]) : t);

export function playerRows(site: Site, rows: unknown[][]): Player[] {
	return rows.map((r) => {
		const p = Object.fromEntries(site.player_fields.map((f, i) => [f, r[i]])) as Record<string, unknown>;
		const season = p.season as number[] | null;
		return {
			...(p as unknown as Player),
			name: decodeEntities(String(p.name ?? '')),
			season: season ? (Object.fromEntries(site.player_season_fields.map((f, i) => [f, season[i]])) as Player['season']) : null,
			locked: p.seasons == null
		};
	});
}

// ---- The column the list is sorted on, as the address has it: a season's rank ("s2026": the
// current season by default), a projected season ("f2028"), "age" (youngest first) or "ga" (goals
// and assists). With the other seasons closed, only the current one can be sorted on.
export function sortKey(asked: string | null, seasons: number[], future: number[], open: boolean): string {
	const now = `s${seasons[0]}`;
	if (asked === 'age' || asked === 'ga') return asked;
	if (!asked || !open) return now;
	const y = Number(asked.slice(1));
	return (asked[0] === 's' && seasons.includes(y)) || (asked[0] === 'f' && future.includes(y)) ? asked : now;
}
// the same for the database: seasons and projected seasons by their place, newest first
const sortParam = (key: string, seasons: number[], future: number[]) =>
	key === 'age' || key === 'ga' ? key : key[0] === 'f' ? `f${future.indexOf(Number(key.slice(1)))}` : `s${seasons.indexOf(Number(key.slice(1)))}`;

// The search, for the database: his name as typed, and for each word the clubs whose search text
// it fits (worked out here, where the clubs' short forms, leagues and countries are known). Each
// word is "word|1 if it fits a player with no club|the ids of the clubs it fits".
export function searchParams(site: Site, all: Club[], facets: Facets, q: string): { p_q: string; p_words: string[] } {
	const byTeam = new Map(all.map((r) => [r.team, r]));
	const fits = (text: string, w: string) => text.includes(' ' + w);
	const clubText = (team: number) => (byTeam.has(team) ? clubSearchText(site, byTeam.get(team)!) : ` ${foldText(teamName(site, team))} `);
	const noClub = ` ${foldText('Team null')} `; // what the old site's search knew a player with no club as
	return {
		p_q: q,
		p_words: foldText(q).split(' ').filter(Boolean).map((w) =>
			`${w}|${fits(noClub, w) ? 1 : 0}|${facets.clubs.filter(([team]) => fits(clubText(team), w)).map(([team]) => team).join(',')}`)
	};
}

export type PlayerChoices = { filter: string; excluded: Set<string>; search: string; sort: string };
const excludedLeagues = (site: Site, ex: Set<string>) => Object.keys(site.competitions).map(Number).filter((id) => isExcluded(site, ex, id));

// What to ask site_players for the list. A search looks at every player, whatever the menu and
// the exclusions say.
export function listParams(site: Site, all: Club[], countries: Country[], cups: Cups, facets: Facets, ch: PlayerChoices): Record<string, unknown> {
	const params: Record<string, unknown> = {};
	const q = ch.search.trim().toLowerCase();
	if (q) Object.assign(params, searchParams(site, all, facets, q));
	else {
		if (isCupFilter(ch.filter)) params.p_teams = [...cupTeams(ch.filter, cups)];
		else { const ids = filterLeagues(ch.filter, countries); if (ids !== null) params.p_leagues = ids; }
		const ex = excludedLeagues(site, ch.excluded);
		if (ex.length) params.p_not_leagues = ex;
	}
	params.p_sort = sortParam(ch.sort, site.player_seasons, site.player_future_seasons);
	return params;
}
// ... and for the numbers in the competition menu: players by league and club, with the
// exclusions applied (the menu's own pick and the search don't count)
export function countParams(site: Site, ex: Set<string>): Record<string, unknown> {
	const not = excludedLeagues(site, ex);
	return { ...(not.length ? { p_not_leagues: not } : {}), p_count: true };
}
// how many players each choice in the menu shows, from [[league, club, players]]
export function playerCounts(counts: [number, number, number][], countries: Country[], cups: Cups): (value: string) => number {
	const byLeague = new Map<number, number>();
	let total = 0;
	for (const [lg, , n] of counts) { byLeague.set(lg, (byLeague.get(lg) || 0) + n); total += n; }
	return (value) => {
		if (value === 'all') return total;
		if (isCupFilter(value)) { const teams = cupTeams(value, cups); return counts.reduce((n, [, team, k]) => n + (teams.has(team) ? k : 0), 0); }
		return (filterLeagues(value, countries) || []).reduce((n, id) => n + (byLeague.get(id) || 0), 0);
	};
}
