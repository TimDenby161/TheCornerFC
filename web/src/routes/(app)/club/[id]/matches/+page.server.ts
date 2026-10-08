import { clubBase, clubFixtures } from '#lib/server/club.ts';
import { clubMove, result, shortDate } from '#lib/club.ts';
import { upcoming } from '#lib/matches.ts';
import { cardView } from '#lib/server/matches.ts';
import { compLabel } from '#lib/site.ts';

const LIMIT = 40;

export async function load({ fetch, params, url, locals }) {
	const { id, site, all, rows, opponent, doc, name } = await clubBase(fetch, params.id);
	const { matches, paywall } = await clubFixtures(fetch, site, id, locals.token);
	const ranks = new Map(all.map((c) => [c.team, c]));
	const next = upcoming(matches);

	// fixtures unless results are asked for, or there are only results
	const view = url.searchParams.get('view') === 'results' || (!next.length && rows.length) ? 'results' : 'fixtures';
	const showAll = url.searchParams.get('all') === '1';
	const thisYear = String(new Date().getFullYear());
	const results = rows.map((m, i) => ({ m, move: clubMove(rows, i, doc?.start ?? null) })).reverse();

	return {
		view, fixtureCount: next.length, resultCount: rows.length, showAll,
		fixtures: view !== 'fixtures' ? [] : next.map((m) => {
			const home = m.home === id;
			return {
				card: cardView(site, ranks, m, paywall), comp: compLabel(site, m.league),
				win: m.p_home != null && m.p_away != null ? Math.round(100 * (home ? m.p_home : m.p_away)) : null
			};
		}),
		results: view !== 'results' ? [] : results.slice(0, showAll ? Infinity : LIMIT).map(({ m, move }) => {
			const home = m.home !== 0;
			const us = { id, name, rank: m.rank }, them = { id: m.opponent, name: opponent(m.opponent), rank: null };
			return {
				key: `${m.date}:${m.opponent}:${m.league}`, res: result(m).toLowerCase(),
				meta: `${shortDate(m.date)}${m.date.slice(0, 4) !== thisYear ? ` '${m.date.slice(2, 4)}` : ''} · ${compLabel(site, m.league)}`,
				home: home ? us : them, away: home ? them : us,
				hg: home ? m.gf : m.ga, ag: home ? m.ga : m.gf,
				homeXg: m.xgf == null ? null : home ? m.xgf : m.xga, awayXg: m.xgf == null ? null : home ? m.xga : m.xgf,
				lines: m.xi_lines, rank: m.rank, attack: m.attack, defence: m.defence, move
			};
		})
	};
}
