import { CLUB_TITLES, filterMenu } from '#lib/clubTable.ts';
import { countParams, playerCounts, type PlayersAnswer } from '#lib/players.ts';
import { keptAsk } from '#lib/server/database.ts';
import { playersBase, playersPage } from '#lib/server/players.ts';

export async function load({ fetch, url, setHeaders }) {
	const base = await playersBase(fetch, url.searchParams);
	const { site, countries, cups, choices, years } = base;
	const [page, counted] = await Promise.all([
		playersPage(fetch, base, 0),
		keptAsk<PlayersAnswer>(fetch, 'site_players', countParams(site, choices.excluded))
	]);
	// the same answer for every visitor who isn't signed in: a shared cache may keep it for a minute
	setHeaders({ 'cache-control': 'public, max-age=60' });

	return {
		...page,
		filter: choices.filter, search: choices.search, sort: choices.sort, years,
		excluded: [...choices.excluded],
		seasons: site.player_seasons, future: site.player_future_seasons,
		menu: filterMenu(site, countries, choices.filter, playerCounts(counted.counts || [], countries, cups), CLUB_TITLES),
		tabHead: {
			title: 'Players',
			intro: "Players ranked by Ability, the model's 0 to 100 estimate of how good each one is now.",
			more: 'terms',
			key: TAB_KEY
		}
	};
}
const TAB_KEY: [string, string][] = [
    ["Ability", "A 0 to 100 estimate of his level, from the clubs he plays for and his own statistics. An average Premier League regular is about 75. The + shows past and projected seasons."],
    ["Pos", "The role he has started in most over his last 20 appearances."],
    ["World", "His place by Ability among every listed player."],
    ["Lg", "His place by Ability among the listed players in his club's league."],
    ["G/A", "Goals and assists this season, for all his clubs."]];
