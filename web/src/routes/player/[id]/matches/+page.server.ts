import { playerBase } from '#lib/server/player.ts';
import { result, shortDate } from '#lib/club.ts';
import { POS_WORD } from '#lib/player.ts';

// His last league appearances, newest first
export async function load({ fetch, params, locals }) {
	const { apps, club } = await playerBase(fetch, params.id, locals.token);
	return {
		matches: apps.map((m) => ({
			key: m.fixture, date: shortDate(m.date), opp: m.opponent, oppName: club(m.opponent), home: !!m.home,
			res: result(m).toLowerCase(), gf: m.gf, ga: m.ga, rank: m.rank,
			card: m.red ? 'red' : m.yellow ? 'yellow' : null,
			bits: [
				`${m.minutes}′${m.started ? '' : ' off the bench'}`, m.started && m.role ? POS_WORD[m.role] || m.role : '',
				m.goals ? `${m.goals} goal${m.goals > 1 ? 's' : ''}` : '', m.assists ? `${m.assists} assist${m.assists > 1 ? 's' : ''}` : ''
			].filter(Boolean)
		}))
	};
}
