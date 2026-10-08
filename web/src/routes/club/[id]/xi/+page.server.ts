import { clubBase, clubSquad } from '#lib/server/club.ts';
import { shortName } from '#lib/club.ts';
import { predictedXi, squadStrength, xiSpots } from '#lib/depth.ts';
import { LIVE } from '#lib/matches.ts';
import { compLabel, teamName } from '#lib/site.ts';

// The next match, the predicted XI on the pitch, and the expected squad's strength. Predicted
// line-ups are for subscribers: a visitor the database sent cut-down data is told so.
export async function load({ fetch, params, locals }) {
	const base = await clubBase(fetch, params.id);
	const { id, site } = base;
	const { depth, next: m, kit, paywall } = await clubSquad(fetch, base, locals.token);
	if (paywall) return { paywall: true as const };
	const xi = predictedXi(depth);
	const ranks = (xi || []).map((c) => c.rank).filter((r): r is number => r != null);
	const home = m ? m.home === id : false, opp = m ? (home ? m.away : m.home) : 0;
	return {
		paywall: false as const, kit,
		spots: !xi ? null : xiSpots(xi).map(({ c, x, y }) => ({
			id: c.p.id, name: shortName(c.p.name), label: c.box.label, x: Math.round(x), y, rank: c.rank, chance: Math.round(c.chance), mins: c.mins,
			tip: `${c.p.name} · ${c.box.label} · rank ${c.rank != null ? c.rank.toFixed(1) : '–'} · ${Math.round(c.chance)}% to start · ${c.mins}′ expected`
		})),
		average: ranks.length ? Math.round(ranks.reduce((t, r) => t + r, 0) / ranks.length) : null,
		squad: squadStrength(depth),
		next: !m ? null : {
			kickoff: m.kickoff, live: LIVE.has(m.status), home, opp, oppName: teamName(site, opp), comp: compLabel(site, m.league),
			win: m.p_home != null && m.p_away != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null,
			gf: m.home_xg != null && m.away_xg != null ? (home ? m.home_xg : m.away_xg) : null,
			ga: m.home_xg != null && m.away_xg != null ? (home ? m.away_xg : m.home_xg) : null,
			xi: (home ? m.home_xi : m.away_xi) ?? null, missing: (home ? m.home_missing : m.away_missing) || 0
		}
	};
}
