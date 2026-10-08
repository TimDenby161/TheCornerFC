// The Stats page: how accurate the model's match predictions have been. The "stats" row holds,
// for each range (7d, 30d, 90d, 365d), the figures for every competition and for all together.
export type MarketStats = { n: number; model_ll: number | null; close_ll: number | null; open_n: number; model_open_ll: number | null; open_ll: number | null };
export type Stats = {
	n: number; live: number; rated: number;
	correct: number | null; exact: number | null; home_rate: number | null; log_loss: number | null; brier: number | null; goal_error: number | null;
	market: { n: number; model_ll: number | null; market_ll: number | null; model_correct: number | null; market_correct: number | null } | null;
	rating_avg: number | null; rating_counts: number[]; factor_avgs: Record<string, number> | null;
	// ten bands of stated chance (0-10%, 10-20% ...): [calls, average said, share that happened]
	calibration: [number, number | null, number | null][];
	markets: Record<string, MarketStats> | null;
};
export type StatsDoc = { ranges: Record<string, Record<string, Stats>> };
export const RANGES = [['7d', '7 days'], ['30d', '30 days'], ['90d', '90 days'], ['365d', '12 months']] as const;
export const MARKET_KEYS = ['1X2', 'BTTS', 'OU15', 'OU25', 'OU35', 'OU45'];
export const MARKET_LABELS: Record<string, string> = { '1X2': 'Result', OU15: 'Over/Under 1.5', OU25: 'Over/Under 2.5', OU35: 'Over/Under 3.5', OU45: 'Over/Under 4.5', BTTS: 'Both teams score' };

// Several competitions' stats as one: counts add up, averages are weighted by what they average over
export function mergeStats(parts: Stats[]): Stats | null {
	if (parts.length < 2) return parts[0] || null;
	const sum = <T>(xs: T[], f: (x: T) => number | null | undefined) => xs.reduce((a, x) => a + (f(x) || 0), 0);
	const avg = <T>(xs: T[], key: keyof T, w: (x: T) => number) => { const n = sum(xs, w); return n ? sum(xs, (x) => (x[key] == null ? 0 : (x[key] as number) * w(x))) / n : null; };
	const n = sum(parts, (x) => x.n), rated = sum(parts, (x) => x.rated);
	const byN = (x: Stats) => x.n;
	const mk = parts.map((x) => x.market).filter((m): m is NonNullable<Stats['market']> => !!m);
	const rating_counts = [0, 1, 2, 3, 4].map((i) => sum(parts, (x) => x.rating_counts?.[i]));
	const fa = parts.filter((x) => x.factor_avgs);
	const markets: Record<string, MarketStats> = {};
	for (const k of MARKET_KEYS) {
		const ms = parts.map((x) => x.markets?.[k]).filter((m): m is MarketStats => !!m);
		if (!ms.length) continue;
		const open = ms.filter((m) => m.open_n);
		markets[k] = { n: sum(ms, (m) => m.n), model_ll: avg(ms, 'model_ll', (m) => m.n), close_ll: avg(ms, 'close_ll', (m) => m.n),
			open_n: sum(open, (m) => m.open_n), model_open_ll: avg(open, 'model_open_ll', (m) => m.open_n), open_ll: avg(open, 'open_ll', (m) => m.open_n) };
	}
	return {
		n, live: sum(parts, (x) => x.live), rated,
		correct: avg(parts, 'correct', byN), exact: avg(parts, 'exact', byN), home_rate: avg(parts, 'home_rate', byN),
		log_loss: avg(parts, 'log_loss', byN), brier: avg(parts, 'brier', byN), goal_error: avg(parts, 'goal_error', byN),
		market: mk.length ? { n: sum(mk, (m) => m.n), model_ll: avg(mk, 'model_ll', (m) => m.n), market_ll: avg(mk, 'market_ll', (m) => m.n),
			model_correct: avg(mk, 'model_correct', (m) => m.n), market_correct: avg(mk, 'market_correct', (m) => m.n) } : null,
		rating_counts, rating_avg: rated ? rating_counts.reduce((a, c, i) => a + (i + 1) * c, 0) / rated : null,
		factor_avgs: rated && fa.length ? Object.fromEntries(Object.keys(fa[0].factor_avgs!).map((k) => [k, sum(fa, (x) => x.factor_avgs![k] * x.rated) / rated])) : null,
		calibration: parts[0].calibration.map((_, i) => {
			const bins = parts.map((x) => x.calibration[i]).filter((b) => b[0]);
			const c = sum(bins, (b) => b[0]);
			return c ? [c, sum(bins, (b) => b[0] * b[1]!) / c, sum(bins, (b) => b[0] * b[2]!) / c] : [0, null, null];
		}),
		markets: Object.keys(markets).length ? markets : null
	};
}
export const pctText = (x: number, d = 1) => `${(100 * x).toFixed(d)}%`;
