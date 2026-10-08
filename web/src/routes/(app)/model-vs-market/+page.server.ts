import { betProbs, betTeams, gbp, onePerPick, summarise, tipLabel, type Bet, type BetsDoc } from '#lib/bets.ts';
import { dayName, GROUP_ORDER, localDay } from '#lib/matchday.ts';
import { matchRows, type MatchesAnswer } from '#lib/matches.ts';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { pctText, type StatsDoc } from '#lib/stats.ts';
import { askAs, keptDoc } from '#lib/server/database.ts';
import { cardView } from '#lib/server/matches.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import { compLabel, type Site } from '#lib/site.ts';

// The paper simulation's open selections (where the model and the market disagree enough for it
// to take one), one per pick, soonest first, grouped by day and competition
export async function load({ fetch, locals, parent, setHeaders }) {
	const { tz } = await parent();
	const [site, rankings, doc, stats] = await Promise.all([
		keptDoc<Site>(fetch, 'site'), keptDoc<RankingsDoc>(fetch, 'rankings'),
		keptDoc<BetsDoc>(fetch, 'bets').catch(() => null), keptDoc<StatsDoc>(fetch, 'stats', 300_000).catch(() => null)
	]);
	const stake = doc?.rules?.stake_gbp ?? 10;
	const picks = onePerPick(doc?.bets || []);
	const now = Date.now();
	const tips = picks.filter((b) => !b.result && Date.parse(b.kickoff) > now).sort((a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff) || a.fixture - b.fixture || a.id - b.id);
	// the top of each card is the match as on the Matches page
	const ids = [...new Set(tips.map((b) => b.fixture))];
	const answer = ids.length ? await askAs<MatchesAnswer>(fetch, locals.token, 'site_matches', { p_ids: ids }).catch(() => null) : null;
	const ranks = new Map(clubs(rankings).map((c) => [c.team, c]));
	const cards = new Map((answer ? matchRows(site.match_fields, answer) : []).map((m) => [m.id, cardView(site, ranks, m, !!answer?.paywall)]));
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });

	// How the model has done against the market: accuracy on every market with odds (last 12
	// months), and the settled paper selections' closing-price record and simulated profit
	const st = stats?.ranges?.['365d']?.all, ms = Object.values(st?.markets || {});
	const s = summarise(picks.filter((b) => b.result === 'win' || b.result === 'loss'), stake);
	const tiles: { ok: boolean | null; pill: string; label: string; value: string; small?: string; rows: [string, string][]; title?: string }[] = [];
	if (ms.length && st) {
		const better = ms.filter((m) => (m.model_ll ?? 9) < (m.close_ll ?? 0)).length, ahead = better > ms.length / 2;
		tiles.push({ ok: ahead, pill: ahead ? 'Ahead' : 'Behind', label: 'Model vs Market', value: String(better), small: `of ${ms.length} markets`,
			rows: [['Matches with odds', Math.max(...ms.map((m) => m.n)).toLocaleString('en-GB')], ...(st.market ? [['Right result, model', pctText(st.market.model_correct ?? 0)], ['Right result, market', pctText(st.market.market_correct ?? 0)]] as [string, string][] : [])],
			title: "Bet markets where the model's log loss beat the closing market fair price, last 12 months" });
	}
	tiles.push({ ok: s.beat == null ? null : s.beat >= 0.5, pill: s.beat == null ? 'No data' : s.beat >= 0.5 ? 'Above 50%' : 'Below 50%', label: 'Beat closing price', value: s.beat == null ? '–' : pctText(s.beat),
		rows: [['Settled selections', String(s.settled || 0)], ['Target', 'Over 50%']],
		title: 'Share of paper selections taken at better odds than the last price before kickoff. Staying above 50% over a large sample would suggest real mispricing; it is not proof on its own' });
	tiles.push({ ok: s.settled ? s.profit >= 0 : null, pill: s.settled && s.roi != null ? `${s.roi > 0 ? '+' : ''}${(100 * s.roi).toFixed(1)}% return` : 'No data', label: 'Simulated profit',
		value: s.settled ? `${s.profit >= 0 ? '+' : '−'}${gbp(Math.abs(s.profit))}` : '–',
		rows: [['Won', s.settled ? `${s.wins} of ${s.settled}` : '–'], ['Strike rate', s.settled ? pctText(s.wins / s.settled) : '–']] });

	const orderOf = (id: number) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
	const group = <K,>(list: Bet[], key: (b: Bet) => K) => { const m = new Map<K, Bet[]>(); for (const b of list) m.set(key(b), [...(m.get(key(b)) || []), b]); return m; };
	return {
		tiles, tabHead: { title: 'Model vs Market', ...TAB_INFO.tips },
		days: [...group(tips, (b) => localDay(b.kickoff, tz))].map(([day, list]) => {
			const comps = group(list, (b) => b.league);
			return {
				key: `d:${day}`, name: dayName(day), count: list.length,
				comps: [...comps.keys()].sort((a, b) => orderOf(a) - orderOf(b) || compLabel(site, a).localeCompare(compLabel(site, b))).map((id) => ({
					key: `c:${day}|${id}`, name: compLabel(site, id), count: comps.get(id)!.length,
					matches: [...group(comps.get(id)!, (b) => b.fixture).values()].map((bs) => ({
						fixture: bs[0].fixture, card: cards.get(bs[0].fixture) ?? null, kickoff: bs[0].kickoff, home: bs[0].home, away: bs[0].away, intl: !!bs[0].intl,
						picks: bs.map((b) => ({ id: b.id, label: tipLabel(b), probs: betProbs(b), odds: b.odds.toFixed(2), teams: betTeams(b) }))
					}))
				}))
			};
		})
	};
}
