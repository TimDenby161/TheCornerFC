import { shortName } from '#lib/club.ts';
import { spots } from '#lib/lineups.ts';
import { nationPredictedXi } from '#lib/nation.ts';
import { injuredPlayers, nationBase } from '#lib/server/nation.ts';

// The predicted XI, read off the current coach's recent team sheets
export async function load({ fetch, params, locals }) {
	const { team, known } = await nationBase(fetch, params.name, locals.token);
	if (!team) return { state: 'none' as const };
	const pred = nationPredictedXi(team, await injuredPlayers(fetch));
	if (!pred) return { state: 'few' as const };
	const name = (pid: number) => team.players[pid] || known.get(pid)?.name || 'Unknown';
	return {
		state: 'xi' as const,
		spots: spots(pred.picks.map((c) => ({ id: c.pid, name: name(c.pid), label: c.role, rank: known.get(c.pid)?.rank ?? null }))),
		out: pred.out.map((pid) => ({ id: pid, name: name(pid), short: shortName(name(pid)), link: known.has(pid) }))
	};
}
