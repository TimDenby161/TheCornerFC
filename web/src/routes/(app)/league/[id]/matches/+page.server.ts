import { leagueRounds, offText, roundLabel } from '#lib/league.ts';
import { dayName, localDay } from '#lib/matchday.ts';
import { FINISHED, LIVE } from '#lib/matches.ts';
import { leagueBase } from '#lib/server/league.ts';

// One round at a time, opening on the round with the next fixture
export async function load({ fetch, params, url, locals, parent }) {
	const { tz } = await parent();
	const { fixtures, club } = await leagueBase(fetch, params.id, locals.token);
	const { rounds, open } = leagueRounds(fixtures);
	if (!rounds.length) return { any: false as const };
	const asked = url.searchParams.get('round');
	const round = asked != null && rounds.includes(asked) ? asked : open!;
	const i = rounds.indexOf(round);
	const byDay = new Map<string, typeof fixtures>();
	for (const f of fixtures.filter((f) => (f.round || '') === round)) { const d = localDay(f.kickoff, tz); byDay.set(d, [...(byDay.get(d) || []), f]); }
	return {
		any: true as const, round, isOpen: round === open,
		rounds: rounds.map((r) => ({ key: r, label: roundLabel(r) })),
		prev: i > 0 ? rounds[i - 1] : null, next: i < rounds.length - 1 ? rounds[i + 1] : null,
		days: [...byDay].map(([d, list]) => ({
			name: dayName(d),
			matches: list.map((f) => {
				const done = f.hg != null && (FINISHED.has(f.status) || LIVE.has(f.status)), over = done && FINISHED.has(f.status);
				return {
					id: f.id, kickoff: f.kickoff, live: LIVE.has(f.status), off: offText(f.status),
					home: { id: f.home, name: club(f.home), won: over && f.hg! > f.ag! }, away: { id: f.away, name: club(f.away), won: over && f.ag! > f.hg! },
					score: done ? `${f.hg}–${f.ag}` : null, pens: done && f.pen_h != null ? `${f.pen_h}–${f.pen_a} pens` : null,
					// before it is played: the model's expected goals and its home, draw and away chances
					xg: !done && f.p_home != null && f.home_xg != null && f.away_xg != null ? `${f.home_xg.toFixed(1)}–${f.away_xg.toFixed(1)}` : null,
					probs: !done && f.p_home != null && f.p_draw != null && f.p_away != null ? `${Math.round(f.p_home * 100)}% · ${Math.round(f.p_draw * 100)}% · ${Math.round(f.p_away * 100)}%` : null
				};
			})
		}))
	};
}
