import { error, json } from '@sveltejs/kit';
import { spells, type PlayerDoc } from '#lib/player.ts';
import { teamName, type Site } from '#lib/site.ts';
import { askAs, keptDoc } from '#lib/server/database.ts';

// A player's clubs season by season, for the tip over a season's rank in the Players table: asked
// for on the first hover over his row. Each season: [club, his rank there, minutes, goals, assists].
export async function GET({ fetch, url, locals, setHeaders }) {
	const id = url.searchParams.get('id') || '';
	if (!/^\d{1,9}$/.test(id)) error(400, 'Bad request');
	const [site, doc] = await Promise.all([
		keptDoc<Site>(fetch, 'site'),
		askAs<PlayerDoc | null>(fetch, locals.token, 'site_player_page', { p_id: Number(id) }).catch(() => null)
	]);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=300' });
	const out: Record<string, [string, number | null, number, number, number][]> = {};
	for (const y of Object.keys(doc?.spells || {}))
		out[y] = spells(doc, y).map((s) => [doc?.teams?.[s.team] || teamName(site, s.team), s.club_rank ?? null, s.minutes ?? 0, s.goals ?? 0, s.assists ?? 0]);
	return json(out);
}
