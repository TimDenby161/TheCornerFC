import { redirect } from '@sveltejs/kit';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { keptDoc } from '#lib/server/database.ts';
import { homeCalls, homeClubs, homeLeagues, homeNations, homePlayers, homeStats, homeXi } from '#lib/server/home.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import type { Site } from '#lib/site.ts';

// Home: what the site is, for a visitor who isn't signed in. A signed-in visitor arriving at the
// bare address goes on to Clubs, as on the old site; the site's name in the menu still opens Home
// for them (a link from one of the site's own pages).
export async function load({ fetch, url, locals, request, parent, setHeaders }) {
	const from = request.headers.get('referer');
	if (locals.user && !(from && new URL(from).origin === url.origin)) redirect(307, '/clubs');
	const { tz } = await parent();
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings')]);
	const all = clubs(doc);
	const [players, calls, stats, nations] = await Promise.all([homePlayers(fetch, site), homeCalls(fetch, site, all, tz), homeStats(fetch), homeNations(fetch)]);
	// The example line-up can need the reconstructed history, which the database takes seconds
	// over: the page doesn't wait for it. The slide joins the turn when it arrives.
	const xi = homeXi(fetch, site, all, tz).catch(() => null);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	return {
		clubCount: all.length, clubs: homeClubs(site, all), players, calls, xi, stats, leagues: homeLeagues(site, all), nations,
		intro: { players: TAB_INFO.players.intro, matches: TAB_INFO.matches.intro, leagues: TAB_INFO.leagues.intro, nations: TAB_INFO.nations.intro }
	};
}
