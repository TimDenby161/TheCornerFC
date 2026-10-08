import { error, json } from '@sveltejs/kit';
import { FPL_ENTRY } from '#lib/fantasy.ts';
import { siteAsk } from '#lib/server/database.ts';

// One of the owner's ticks on the FPL page (in my team, a target), saved to their account. The
// database refuses anyone else.
export async function POST({ fetch, locals, request }) {
	if (!locals.token) error(401, 'Sign in first');
	const b = await request.json().catch(() => null);
	if (!b || !Number.isInteger(b.player)) error(400, 'Bad request');
	const res = await siteAsk(fetch, 'mark_fpl_player', { p_entry: FPL_ENTRY, p_player: b.player, p_mine: !!b.mine, p_target: !!b.target }, locals.token)
		.catch(() => ({ ok: false, error: "Couldn't save that just now." }));
	return json(res);
}
