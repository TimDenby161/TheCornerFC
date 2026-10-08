import { error } from '@sveltejs/kit';
import { appearances, seasonLines, sumSeason, type PlayerDoc } from '#lib/player.ts';
import { playerRows, type PlayersAnswer } from '#lib/players.ts';
import { teamName, type Site } from '#lib/site.ts';
import { askAs, keptDoc } from './database.ts';

// What every part of a player's page starts from: his row in the Players list and his own file,
// both as this visitor may see them (`token`: theirs, if signed in). A player who isn't in the
// current ranks has no page.
export async function playerBase(fetch: typeof globalThis.fetch, param: string, token?: string) {
	if (!/^\d{1,9}$/.test(param)) error(404, 'Not found');
	const id = Number(param);
	const site = await keptDoc<Site>(fetch, 'site');
	const [answer, doc] = await Promise.all([
		askAs<PlayersAnswer>(fetch, token, 'site_players', { p_ids: [id], p_limit: 1 }),
		askAs<PlayerDoc | null>(fetch, token, 'site_player_page', { p_id: id }).catch(() => null)
	]);
	const p = playerRows(site, answer.rows)[0];
	if (!p) error(404, 'Not found');
	const year = site.player_seasons[0];
	const lines = seasonLines(doc), apps = appearances(doc);
	// his league minutes and stats this season, all his clubs (none yet: zero minutes)
	const now = doc ? sumSeason(lines.filter((r) => r.season === year)) ?? { apps: null, starts: null, minutes: 0, goals: null, assists: null, yellow: null, red: null } : null;
	// a club's name as his file has it (clubs the names row doesn't hold), else the site's
	const club = (t: number) => doc?.teams?.[t] || teamName(site, t);
	return { id, site, p, doc, lines, apps, now, year, club };
}
