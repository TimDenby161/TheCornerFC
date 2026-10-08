import { bankAfter, BET_MARKETS, betProbs, betScope, betTeams, gbp, SEL_LABELS, signedGbp, summarise, type Bet, type BetChoices, type BetsDoc, type Summary } from '#lib/bets.ts';
import { filterMenu } from '#lib/clubTable.ts';
import { compCountries, filterComps, knownMatchFilter } from '#lib/matchday.ts';
import { MARKET_LABELS, pctText } from '#lib/stats.ts';
import { keptDoc } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import { compLabel, type Site } from '#lib/site.ts';

const TITLES = {
	all: 'All competitions', country: (c: string) => `All ${c} bets`, region: (r: string) => `All bets in ${r}`,
	euro: 'Champions League, Europa League and Conference League bets', cup: (name: string) => `${name} bets`, intl: 'Bets on national team matches'
};

// A record of the paper selections as if each had been backed with the same paper stake
export async function load({ fetch, url, locals, setHeaders }) {
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<BetsDoc>(fetch, 'bets').catch(() => null)]);
	const q = url.searchParams;
	const pick = <T extends string>(k: string, ok: readonly T[], def: T): T => (ok.includes(q.get(k) as T) ? (q.get(k) as T) : def);
	const ch: BetChoices = { strategy: pick('s', ['all', 'early', 'late'], 'all'), market: pick('m', ['all', ...BET_MARKETS], 'all'), view: pick('v', ['all', 'cautious'], 'all') };
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const tabHead = { title: 'Paper Simulation', ...TAB_INFO.bets };
	if (!doc) return { ...ch, filter: 'all', menu: null, tabHead, any: false as const };

	const stake = doc.rules?.stake_gbp ?? 10, bank = doc.rules?.bank ?? 1000;
	const countries = compCountries(site, doc.bets.map((b) => b.league));
	const intl = [...new Set(doc.bets.filter((b) => b.intl).map((b) => b.league))].filter((id) => site.competitions[id]?.type === 'International');
	const filter = knownMatchFilter(q.get('c'), site, countries) ? q.get('c')! : 'all';
	const scope = betScope(doc.bets, ch);
	// the menu shows how many settled bets each competition, country and region has on those choices
	const done = scope.filter((b) => b.result === 'win' || b.result === 'loss');
	const menu = filterMenu(site, countries, filter, (value) => { const ids = filterComps(value, countries, intl); return ids ? done.filter((b) => ids.includes(b.league)).length : done.length; }, TITLES, intl);
	const ids = filterComps(filter, countries, intl);
	const all = ids ? scope.filter((b) => ids.includes(b.league)) : scope;
	const s = summarise(all, stake);

	const line = (label: string, x: Summary, o: { league?: number; on?: boolean } = {}) => ({
		label, ...o, bets: x.settled, pending: x.pending, won: x.settled ? `${x.wins}/${x.settled}` : '–',
		profit: x.settled ? { text: signedGbp(x.profit), cls: x.profit > 0 ? 'pos' : x.profit < 0 ? 'neg' : '' } : null,
		roi: x.roi == null ? null : { text: `${x.roi > 0 ? '+' : ''}${(100 * x.roi).toFixed(1)}%`, cls: x.roi > 0 ? 'pos' : x.roi < 0 ? 'neg' : '' }
	});
	const byLeague = new Map<number, Bet[]>();
	for (const b of all) byLeague.set(b.league, [...(byLeague.get(b.league) || []), b]);
	const after = bankAfter(all, stake, bank);
	const settled = all.filter((b) => b.result).sort((a, b) => Date.parse(b.kickoff) - Date.parse(a.kickoff) || b.id - a.id);
	return {
		...ch, filter, menu, tabHead, any: true as const, empty: !all.length,
		stake: gbp(stake), bank: gbp(bank), minEdge: Math.round(doc.rules.min_edge * 100), maxOdds: doc.rules.max_odds, pending: s.pending,
		cards: [
			['Simulated bank', gbp(bank + s.profit), `Started with ${gbp(bank)}${s.pending ? ` · ${gbp(s.atRisk)} on ${s.pending} pending` : ''}`, ''],
			['Simulated profit', s.settled ? signedGbp(s.profit) : '–', s.staked && s.roi != null ? `${gbp(s.staked)} staked · return ${(s.roi > 0 ? '+' : '') + (100 * s.roi).toFixed(1)}%` : `${gbp(stake)} on every bet`, s.settled ? (s.profit > 0 ? 'pos' : s.profit < 0 ? 'neg' : '') : ''],
			['Won', s.settled ? `${s.wins}` : '–', s.settled ? `${pctText(s.wins / s.settled)} of settled bets` : 'Needs settled bets', s.settled ? `of ${s.settled}` : ''],
			['Beat the closing price', s.beat == null ? '–' : pctText(s.beat), 'Took better odds than the last price before kickoff. Only means something over a large sample, and is not proof of value on its own', '']
		],
		// (leagues level on bets stay in the order of their ids, as on the old site)
		leagues: [...byLeague].sort((a, b) => a[0] - b[0]).map(([id, bs]) => [id, summarise(bs, stake)] as const).sort((a, b) => b[1].settled - a[1].settled || b[1].placed - a[1].placed)
			.map(([id, x]) => line(compLabel(site, id), x, { league: id, on: String(id) === filter })),
		markets: BET_MARKETS.map((mk) => [mk, summarise(all.filter((b) => b.market === mk), stake)] as const).filter(([, x]) => x.placed).map(([mk, x]) => line(MARKET_LABELS[mk], x)),
		settledCount: settled.length,
		settled: settled.slice(0, 300).map((b) => ({
			id: b.id, kickoff: b.kickoff, comp: compLabel(site, b.league), when: b.strategy === 'early' ? 'Night before' : 'Pre-kickoff', result: b.result,
			match: `${b.home} v ${b.away}`, score: b.score, teams: betTeams(b), intl: !!b.intl, pick: SEL_LABELS[b.selection] || b.selection, odds: b.odds.toFixed(2),
			outcome: b.result === 'win' ? { text: `Won +${gbp(stake * (b.profit || 0))}`, cls: 'pos' } : b.result === 'loss' ? { text: `Lost −${gbp(stake)}`, cls: 'neg' } : { text: 'Void, stake back', cls: '' },
			sub: `${betProbs(b)}${b.closing_odds != null ? ` · closed ${b.closing_odds.toFixed(2)}` : ''}${after.has(b.id) ? ` · simulated bank ${gbp(after.get(b.id))}` : ''}`
		}))
	};
}
