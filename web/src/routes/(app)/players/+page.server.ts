import { TAB_INFO } from '#lib/tabInfo.ts';
import { CLUB_TITLES, filterMenu } from '#lib/clubTable.ts';
import { countryDisplay } from '#lib/clubTable.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { GROUP_SINGLE, PITCH_SPOTS, RANGES, rangeStops, stopIndex, type RangeKey } from '#lib/playerFilters.ts';
import { countParams, playerCounts, type PlayersAnswer } from '#lib/players.ts';
import { teamName } from '#lib/site.ts';
import { keptAsk } from '#lib/server/database.ts';
import { playersBase, playersPage } from '#lib/server/players.ts';

export async function load({ fetch, url, setHeaders, locals }) {
	const base = await playersBase(fetch, url.searchParams);
	const { site, all, facets, countries, cups, choices, years, groups } = base;
	const [page, counted] = await Promise.all([
		playersPage(fetch, base, 0, locals.token),
		keptAsk<PlayersAnswer>(fetch, 'site_players', countParams(site, choices))
	]);
	// the same answer for every visitor who isn't signed in: a shared cache may keep it for a minute
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });

	// each slider: its stops and where its two handles stand
	const slider = (k: RangeKey) => {
		const stops = rangeStops(k, facets, all.length), r = choices.ranges[k];
		return { stops, a: stopIndex(stops, r[0], 0), b: stopIndex(stops, r[1], 1) };
	};

	return {
		...page,
		sliders: { age: slider('age'), ab: slider('ab'), crank: slider('crank'), mins: slider('mins') },
		rangeInfo: RANGES,
		positions: choices.positions, groups, groupNames: groups.map((g) => GROUP_SINGLE[g]),
		pitch: PITCH_SPOTS.map(([pos, x, y]) => ({ pos, x, y, n: facets.positions[pos] || 0 })),
		clubs: choices.clubs.map((id) => ({ id, name: teamName(site, id) })),
		nats: choices.nats.map((name) => ({ name, flag: FLAG_CODES[countryDisplay(name)] ?? null })),
		filter: choices.filter, search: choices.search, sort: choices.sort, years,
		excluded: [...choices.excluded],
		seasons: site.player_seasons, future: site.player_future_seasons,
		menu: filterMenu(site, countries, choices.filter, playerCounts(counted.counts || [], countries, cups), CLUB_TITLES),
		tabHead: { title: 'Players', ...TAB_INFO.players }
	};
}
