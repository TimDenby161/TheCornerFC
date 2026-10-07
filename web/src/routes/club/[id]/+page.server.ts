import { clubBase, clubFixtures } from '#lib/server/club.ts';
import { keptDoc } from '#lib/server/database.ts';
import { clubMove, shortDate } from '#lib/club.ts';
import { LIVE, upcoming } from '#lib/matches.ts';
import { compLabel, leagueShort, teamName } from '#lib/site.ts';

// The injury lists: per club, its next match's, else its latest recent one. A row is
// [player, name, type, ban, matches missed in a row, season rank]; the injury itself isn't published.
type Injuries = { teams: Record<string, { kickoff: string; upcoming: boolean; players: [number, string, string, string | null, number, number | null][] }> };
const BAN_REASONS = new Set(['Red Card', 'Yellow Cards', 'Suspended']);

export async function load({ fetch, params }) {
	const { id, site, rows, opponent, doc } = await clubBase(fetch, params.id);
	const [{ matches }, injuries] = await Promise.all([
		clubFixtures(fetch, site, id),
		keptDoc<Injuries>(fetch, 'injuries', 300_000).catch(() => null)
	]);
	const next = upcoming(matches);
	const side = (m: (typeof next)[number]) => {
		const home = m.home === id, opp = home ? m.away : m.home;
		const gf = m.home_xg != null && m.away_xg != null ? (home ? m.home_xg : m.away_xg) : null;
		const ga = m.home_xg != null && m.away_xg != null ? (home ? m.away_xg : m.home_xg) : null;
		return { home, opp, oppName: teamName(site, opp), gf, ga, win: m.p_home != null && m.p_away != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null };
	};

	const m = next[0];
	const inj = injuries?.teams?.[String(id)] ?? null;
	const past = inj && !inj.upcoming ? rows.find((r) => r.date === inj.kickoff.slice(0, 10)) : null;

	return {
		next: m ? {
			...side(m), kickoff: m.kickoff, live: LIVE.has(m.status), comp: compLabel(site, m.league),
			xi: (m.home === id ? m.home_xi : m.away_xi) ?? null,
			missing: (m.home === id ? m.home_missing : m.away_missing) || 0
		} : null,
		injuries: !inj ? null : {
			upcoming: inj.upcoming, kickoff: inj.kickoff,
			latest: past ? `${past.home ? 'v' : '@'} ${opponent(past.opponent)}` : null,
			// best first by rank
			players: inj.players.slice().sort((a, b) => (b[5] ?? -1) - (a[5] ?? -1)).map(([pid, name, type, ban, missed, rank]) => ({
				id: pid, name, missed, rank,
				note: type === 'Questionable' ? 'doubt' as const : type === 'Suspended' || (ban && BAN_REASONS.has(ban)) ? 'susp' as const : null,
				ban: ban && BAN_REASONS.has(ban) && ban !== 'Suspended' ? ban : null
			}))
		},
		// the fixtures after it
		fixtures: next.slice(0, 5).map((f) => {
			const s = side(f);
			return {
				id: f.id, kickoff: f.kickoff, ...s, league: f.league, comp: leagueShort(site, f.league), compFull: compLabel(site, f.league),
				cs: s.ga != null ? Math.round(100 * Math.exp(-s.ga)) : null
			};
		}),
		// the last ten results, newest first
		results: rows.slice(-10).map((r, k, arr) => ({
			date: r.date, gf: r.gf, ga: r.ga, opp: r.opponent, oppName: opponent(r.opponent), where: r.home === 2 ? 'N' : r.home ? 'H' : 'A',
			neutral: r.home === 2, home: !!r.home, league: r.league, comp: compLabel(site, r.league),
			xgf: r.xgf, xga: r.xga, est: !!r.xg_est, move: clubMove(rows, rows.length - arr.length + k, doc?.start ?? null),
			title: `${shortDate(r.date)} ${r.home ? 'v' : '@'} ${opponent(r.opponent)}${r.home === 2 ? ' (neutral)' : ''} · ${compLabel(site, r.league)}`
		})).reverse()
	};
}
