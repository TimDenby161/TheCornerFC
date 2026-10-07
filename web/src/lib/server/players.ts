import { shortName } from '#lib/club.ts';
import { countryDisplay, isExcludeKey, knownFilter, tableCountries } from '#lib/clubTable.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { listParams, playerRows, sortKey, type Facets, type Player, type PlayersAnswer } from '#lib/players.ts';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { leagueShort, teamName, type Site } from '#lib/site.ts';
import { loadCups } from './cups.ts';
import { keptAsk, keptDoc } from './database.ts';

export const PAGE_ROWS = 100;
const POS_LABEL: Record<string, string> = { G: 'GK', D: 'DEF', M: 'MID', F: 'FWD' };

// What the Players page and its "more rows" requests both start from: the names, the clubs, the
// cups, what the filters can offer, and the page's choices as its address has them.
export async function playersBase(fetch: typeof globalThis.fetch, q: URLSearchParams) {
	const [site, doc, cups, facets] = await Promise.all([
		keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings'), loadCups(fetch),
		keptAsk<Facets>(fetch, 'site_player_facets', {}, 300_000)
	]);
	const all = clubs(doc);
	const countries = tableCountries(site, all);
	const years = q.get('y') === '1';
	const choices = {
		filter: knownFilter(q.get('c'), site, countries) ? q.get('c')! : 'all',
		excluded: new Set((q.get('ex') || '').split('|').filter(isExcludeKey)),
		search: (q.get('q') || '').slice(0, 80),
		sort: sortKey(q.get('sort'), site.player_seasons, site.player_future_seasons, years)
	};
	return { site, all, cups, facets, countries, years, choices };
}

// A page of the list from `offset`, as a visitor who isn't signed in sees it
export async function playersPage(fetch: typeof globalThis.fetch, base: Awaited<ReturnType<typeof playersBase>>, offset: number) {
	const { site, all, countries, cups, facets, choices } = base;
	const answer = await keptAsk<PlayersAnswer>(fetch, 'site_players', { ...listParams(site, all, countries, cups, facets, choices), p_limit: PAGE_ROWS, p_offset: offset });
	return { total: answer.total, paywall: !!answer.paywall, rows: playerRows(site, answer.rows).map((p) => rowView(site, p)) };
}

// A player's row as the page draws it, names and all
export type PlayerRow = ReturnType<typeof rowView>;
function rowView(site: Site, p: Player) {
	return {
		id: p.id, name: p.name, short: shortName(p.name),
		team: p.team, teamName: p.team ? teamName(site, p.team) : null,
		league: p.league != null ? leagueShort(site, p.league) : '',
		nat: p.nationality, flag: p.nationality ? FLAG_CODES[countryDisplay(p.nationality)] ?? FLAG_CODES[p.nationality] ?? null : null,
		pos: (p.position && POS_LABEL[p.position]) || p.position || '',
		age: p.age, world: p.world, lg: p.lg, lgOf: p.lg_of,
		ga: p.season ? [p.season.goals, p.season.assists] : null,
		seasons: p.seasons, estimated: p.estimated || [], future: p.future
	};
}
