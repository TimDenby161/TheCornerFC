import { error, json } from '@sveltejs/kit';
import { FPL_ENTRY } from '#lib/fantasy.ts';
import { siteAsk } from '#lib/server/database.ts';

// "I've made these transfers" on My FPL team (and its Undo): a lock for the gameweek, saved to the
// owner's account. The database refuses anyone else.
export async function POST({ fetch, locals, request }) {
	if (!locals.token) error(401, 'Sign in first');
	const b = await request.json().catch(() => null);
	if (!b || !Number.isInteger(b.event) || b.season == null) error(400, 'Bad request');
	const args = { p_entry: FPL_ENTRY, p_season: b.season, p_event: b.event };
	const res = await siteAsk(fetch, b.undo ? 'unlock_fpl_transfers' : 'lock_fpl_transfers',
		b.undo ? args : { ...args, p_transfers: Array.isArray(b.transfers) ? b.transfers : [] }, locals.token)
		.catch(() => ({ ok: false, error: "Couldn't reach the database: nothing was saved." }));
	return json(res);
}
