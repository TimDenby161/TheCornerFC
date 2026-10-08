import { filterMenu } from '#lib/clubTable.ts';
import { compCountries, filterComps, knownMatchFilter } from '#lib/matchday.ts';
import { MARKET_KEYS, MARKET_LABELS, mergeStats, pctText, RANGES, type Stats, type StatsDoc } from '#lib/stats.ts';
import { keptDoc } from '#lib/server/database.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';
import type { Site } from '#lib/site.ts';

const TITLES = {
	all: 'All competitions', country: (c: string) => `All ${c} competitions`, region: (r: string) => `All competitions in ${r}`,
	euro: 'Champions League, Europa League and Conference League', cup: (name: string) => name,
	intl: 'National team matches: World Cup, qualifiers, Nations League, friendlies and others'
};
const RATING_LABELS: Record<number, string> = { 1: 'Terrible', 2: 'Poor', 3: 'Decent', 4: 'Very good', 5: 'Excellent' };
const FACTORS = [['winner', 'Winner', '30%'], ['margin', 'Margin', '25%'], ['clean_sheets', 'Clean sheets', '20%'], ['shape', 'Shape', '15%'], ['goals', 'Goals', '10%']];

export async function load({ fetch, url, locals, setHeaders }) {
	const [site, doc] = await Promise.all([keptDoc<Site>(fetch, 'site'), keptDoc<StatsDoc>(fetch, 'stats', 300_000)]);
	// every competition with stats in any range, so the menu stays put when the range changes
	const ids = [...new Set(Object.values(doc.ranges).flatMap(Object.keys).filter((k) => /^\d+$/.test(k)))].map(Number);
	const n = (id: number) => doc.ranges['365d']?.[id]?.n || 0;
	const countries = compCountries(site, ids);
	const intl = ids.filter((id) => site.competitions[id]?.type === 'International').sort((a, b) => n(b) - n(a) || a - b);
	const q = url.searchParams;
	const filter = knownMatchFilter(q.get('c'), site, countries) ? q.get('c')! : 'all';
	const range = RANGES.some(([k]) => k === q.get('r')) ? q.get('r')! : '30d';
	const menu = filterMenu(site, countries, filter, null, TITLES, intl);
	const all = doc.ranges[range];
	const picked = filterComps(filter, countries, intl);
	const s: Stats | null = !all ? null : picked ? mergeStats(picked.map((id) => all[id]).filter(Boolean)) : all.all ?? null;
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	const base = { filter, range, ranges: RANGES, menu, tabHead: { title: 'Stats', ...TAB_INFO.stats } };
	if (!s) return { ...base, stats: null };

	const rc = s.rating_counts || [0, 0, 0, 0, 0], rated = rc.reduce((a, b) => a + b, 0);
	const mk = s.market, better = (a: number | null, b: number | null, lower = false) => a != null && b != null && (lower ? a < b : a > b);
	const gap = (model: number | null, book: number | null) => { if (model == null || book == null) return null; const d = model - book; return { text: `${d > 0 ? '+' : ''}${d.toFixed(3)}`, cls: d < 0 ? 'pos' : d > 0 ? 'neg' : '' }; };
	return {
		...base,
		stats: {
			cards: [
				['Matches', s.n.toLocaleString('en-GB'), s.live === s.n ? 'All recorded before kickoff' : s.live === 0 ? 'Reconstructed from pre-match data' : `${s.live.toLocaleString('en-GB')} recorded before kickoff, rest reconstructed`],
				['Right result', pctText(s.correct ?? 0), `Picking the home team every time: ${pctText(s.home_rate ?? 0)}`],
				['Exact score', pctText(s.exact ?? 0), 'Most likely scoreline was spot on'],
				['Goal error', (s.goal_error ?? 0).toFixed(2), 'Average goals off per team'],
				['Log loss', (s.log_loss ?? 0).toFixed(3), 'Lower is better. Guessing ≈ 1.07'],
				['Brier score', (s.brier ?? 0).toFixed(3), 'Lower is better. Guessing ≈ 0.64']
			],
			market: !mk ? null : {
				n: mk.n, small: mk.n < 1000,
				right: { model: pctText(mk.model_correct ?? 0), market: pctText(mk.market_correct ?? 0), modelBetter: better(mk.model_correct, mk.market_correct), marketBetter: better(mk.market_correct, mk.model_correct) },
				ll: { model: (mk.model_ll ?? 0).toFixed(3), market: (mk.market_ll ?? 0).toFixed(3), modelBetter: better(mk.model_ll, mk.market_ll, true), marketBetter: better(mk.market_ll, mk.model_ll, true) }
			},
			// the model against the market in every bet market: log loss on the same matches against the
			// closing prices, and against opening prices where the odds were first seen before kickoff
			markets: !mk || !s.markets ? [] : MARKET_KEYS.filter((k) => s.markets![k]).map((k) => {
				const m = s.markets![k];
				return { label: MARKET_LABELS[k], n: m.n, model: (m.model_ll ?? 0).toFixed(3), close: (m.close_ll ?? 0).toFixed(3), gap: gap(m.model_ll, m.close_ll), open: m.open_n ? { gap: gap(m.model_open_ll, m.open_ll), n: m.open_n } : null };
			}),
			calibration: s.calibration.flatMap(([count, said, hit], i) => count && said != null && hit != null ? [{
				band: `${i * 10}–${i * 10 + 10}%`, count, said: pctText(said), hit: pctText(hit), bar: Math.round(hit * 60),
				cls: Math.abs(hit - said) <= 0.03 ? 'gap-ok' : Math.abs(hit - said) > 0.06 ? 'gap-off' : ''
			}] : []),
			rating: !rated || s.rating_avg == null ? null : {
				avg: s.rating_avg.toFixed(2), label: RATING_LABELS[Math.round(s.rating_avg)],
				dist: [5, 4, 3, 2, 1].map((r) => ({ r, label: `${r} ${RATING_LABELS[r]}`, share: Math.round((100 * rc[r - 1]) / rated), pct: pctText(rc[r - 1] / rated, 0) })),
				factors: s.factor_avgs ? FACTORS.map(([k, label, weight]) => ({ label, weight, value: s.factor_avgs![k].toFixed(2), share: Math.round((s.factor_avgs![k] / 5) * 100) })) : []
			}
		}
	};
}
