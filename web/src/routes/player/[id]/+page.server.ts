import { playerBase } from '#lib/server/player.ts';
import { clubFixtures } from '#lib/server/club.ts';
import { GROUP_OF } from '#lib/playerFilters.ts';
import { LIVE, upcoming } from '#lib/matches.ts';
import { positionChips } from '#lib/player.ts';
import { compLabel, teamName } from '#lib/site.ts';

const BAN_REASONS = new Set(['Red Card', 'Yellow Cards', 'Suspended']);

export async function load({ fetch, params, locals }) {
	const { site, p, doc } = await playerBase(fetch, params.id, locals.token);
	// his club's next match: when, who, the model's view, and whether he is listed unavailable for
	// it (the injury itself isn't published: only "Doubtful", "Suspended" or "Out")
	const m = p.team ? upcoming((await clubFixtures(fetch, site, p.team, locals.token)).matches)[0] : null;
	const inj = doc?.injury;
	let next = null;
	if (m && p.team) {
		const home = m.home === p.team, opp = home ? m.away : m.home;
		next = {
			kickoff: m.kickoff, live: LIVE.has(m.status), home, opp, oppName: teamName(site, opp), comp: compLabel(site, m.league),
			win: m.p_home != null && m.p_away != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null,
			proj: m.home_xg != null && m.away_xg != null ? `${(home ? m.home_xg : m.away_xg).toFixed(1)}–${(home ? m.away_xg : m.home_xg).toFixed(1)}` : '',
			status: inj && inj[0] === m.id
				? { cls: inj[1] === 'Questionable' ? 'warn' : 'bad', text: inj[1] === 'Questionable' ? 'Doubtful' : inj[1] === 'Suspended' || (inj[2] && BAN_REASONS.has(inj[2])) ? 'Suspended' : 'Out' }
				: null
		};
	}
	return {
		next,
		chips: positionChips(p.position, p.rank, p.position_ranks, doc?.positions),
		keeper: !!p.position && GROUP_OF[p.position] === 'GK',
		hasFile: !!doc,
		listed: inj ? (inj[1] === 'Questionable' ? 'doubtful' : inj[1] === 'Suspended' || (inj[2] && BAN_REASONS.has(inj[2])) ? 'suspended' : 'out') : null
	};
}
