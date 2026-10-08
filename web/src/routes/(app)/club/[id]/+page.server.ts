import { clubBase, clubSquad } from '#lib/server/club.ts';
import { clubMove, shortDate, shortName } from '#lib/club.ts';
import { LIVE, upcoming } from '#lib/matches.ts';
import { compLabel, leagueShort, teamName } from '#lib/site.ts';

const BAN_REASONS = new Set(['Red Card', 'Yellow Cards', 'Suspended']);

export async function load({ fetch, params, locals }) {
	const base = await clubBase(fetch, params.id);
	const { id, site, rows, opponent, doc } = base;
	const { depth, list, inj, kit, matches } = await clubSquad(fetch, base, locals.token);
	const byId = new Map(list.map((p) => [p.id, p]));
	const next = upcoming(matches);
	const side = (m: (typeof next)[number]) => {
		const home = m.home === id, opp = home ? m.away : m.home;
		const gf = m.home_xg != null && m.away_xg != null ? (home ? m.home_xg : m.away_xg) : null;
		const ga = m.home_xg != null && m.away_xg != null ? (home ? m.away_xg : m.home_xg) : null;
		return { home, opp, oppName: teamName(site, opp), gf, ga, win: m.p_home != null && m.p_away != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null };
	};

	const m = next[0];
	const nextLabel = m ? leagueShort(site, m.league) : '';
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
			players: inj.players.map((row) => [row, byId.get(row[0])?.rank ?? row[5] ?? null] as const).sort((a, b) => (b[1] ?? -1) - (a[1] ?? -1)).map(([[pid, name, type, ban, missed], rank]) => ({
				id: pid, name, missed, rank,
				note: type === 'Questionable' ? 'doubt' as const : type === 'Suspended' || (ban && BAN_REASONS.has(ban)) ? 'susp' as const : null,
				ban: ban && BAN_REASONS.has(ban) && ban !== 'Suspended' ? ban : null
			}))
		},
		// the squad by position: each box's players, best first, with the chance each starts there
		// in the next match and the minutes he is expected to play
		pitch: !depth ? null : {
			kit,
			boxes: depth.shown.map((b) => ({
				label: b.label, n: b.n, row: b.row === '3 / span 2' ? '3s2' : String(b.row), col: b.col, total: depth.boxMins.get(b.label) || 0,
				rows: b.ps.map(({ p, rank }) => {
					const got = Math.round(depth.startChance.get(`${b.label}:${p.id}`) || 0), xmin = depth.xMins.get(`${b.label}:${p.id}`) || 0;
					const bench = depth.benchRate(p);
					return {
						id: p.id, name: shortName(p.name), pct: got || null, rank: Math.round(rank ?? 0), xmin,
						tip: `${p.name}: ${got}% chance of starting at ${b.label} in the next match${nextLabel ? ` (${nextLabel})` : ''} (started ${depth.startPct(p, b.roles) || 0}% of this season's matches there${b.proj?.changed ? '; allowing for the injured or departed' : ''})`
							+ ((depth.picks.get(b.label) || []).includes(p.id) ? ' · in the best XI by rating' : '')
							+ ` · xMins ${xmin}: lasts ${Math.round(depth.lasts(p))}′ when he starts${bench ? `, ${Math.round(bench)}′ a match off the bench` : ''}`
					};
				})
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
