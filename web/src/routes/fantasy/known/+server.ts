import { error, json } from '@sveltejs/kit';
import { siteAsk, keptDoc } from '#lib/server/database.ts';
import type { PlayersAnswer } from '#lib/players.ts';
import type { Site } from '#lib/site.ts';

// Which of these players are in the Players list, and so have a page of their own to link to
export async function POST({ fetch, locals, request }) {
	if (!locals.token) error(401, 'Sign in first');
	const b = await request.json().catch(() => null);
	const ids = Array.isArray(b?.ids) ? b.ids.filter((x: unknown) => Number.isInteger(x)).slice(0, 1000) : [];
	if (!ids.length) return json({ ids: [] });
	const [site, d] = await Promise.all([
		keptDoc<Site>(fetch, 'site'),
		siteAsk<PlayersAnswer>(fetch, 'site_players', { p_ids: ids, p_limit: ids.length }, locals.token)
	]);
	const at = site.player_fields.indexOf('id');
	return json({ ids: d.rows.map((r) => r[at]) });
}
