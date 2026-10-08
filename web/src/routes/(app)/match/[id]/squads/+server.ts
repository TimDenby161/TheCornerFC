import { json } from '@sveltejs/kit';
import { squadStrength } from '#lib/depth.ts';
import { FINISHED, LIVE, NO_GAME } from '#lib/matches.ts';
import { clubBase, clubSquad } from '#lib/server/club.ts';
import { matchBase } from '#lib/server/match.ts';

// Both clubs' expected squads for an upcoming match (their attack, defence and overall rating,
// from expected minutes), asked for when its card comes into view. They rest on the players'
// ranks, so a visitor the database sends cut-down data gets none.
export async function GET({ fetch, params, locals }) {
	const { m, paywall } = await matchBase(fetch, params.id, locals.token);
	const headers = { 'cache-control': 'private, no-store' };
	const upcoming = !(FINISHED.has(m.status) && m.hg != null) && !LIVE.has(m.status) && !NO_GAME.has(m.status);
	if (!upcoming || m.intl || paywall) return json(null, { headers });
	const side = async (teamId: number, recent: number | null) => {
		const base = await clubBase(fetch, String(teamId)).catch(() => null);
		if (!base) return null;
		const sq = await clubSquad(fetch, base, locals.token, m.league);
		const s = sq.paywall ? null : squadStrength(sq.depth);
		if (!s || s.attack == null || s.defence == null) return null;
		const now = Math.round(s.strength);
		return { attack: Math.round(s.attack), defence: Math.round(s.defence), strength: now, recent: recent == null ? null : Math.round(recent),
			trend: recent == null ? '' : now > Math.round(recent) ? 'good' : now < Math.round(recent) ? 'bad' : 'same' };
	};
	const [home, away] = await Promise.all([side(m.home, m.home_recent_xi), side(m.away, m.away_recent_xi)]);
	return json(home && away ? { home, away } : null, { headers });
}
