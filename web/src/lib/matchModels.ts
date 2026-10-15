// The two match models that run side by side (MC-0029, db/migrations/20261014_challenger_model.sql):
// the switch in the Admin area names the live one, which the site and the paper bets use.
export const MATCH_MODELS = ['base', 'a18'] as const;
export type MatchModelName = (typeof MATCH_MODELS)[number];
export const MATCH_MODEL_LABELS: Record<MatchModelName, string> = {
	base: 'The base model (club rank with movers, new clubs and shots)',
	a18: 'The base model with A18’s boosted trees'
};
export const isMatchModel = (value: unknown): value is MatchModelName => MATCH_MODELS.includes(value as MatchModelName);
// The model the button offers: the one that is not live
export const otherModel = (live: MatchModelName): MatchModelName => (live === 'base' ? 'a18' : 'base');

// The two models compared, for the switch card (admin_match_model_compare(),
// db/migrations/20261014_match_model_compare.sql). Chances are 0 to 1; a row's five numbers are
// home, draw and away chances, then home and away expected goals.
export type ModelScore = { n: number; log_loss: number; brier: number; accuracy: number };
export type ApartRow = { fixture: number; kickoff: string; league: string; home: string; away: string; differ: boolean; gap: number; base: number[]; a18: number[]; market?: number[] | null };
export type ModelCompare = {
	start: string;
	// base and a18 on every finished match; market, base_priced and a18_priced on those with stored prices
	finished: Partial<Record<MatchModelName | 'market' | 'base_priced' | 'a18_priced', ModelScore>>;
	upcoming: { n: number; different_favourite: number; mean_gap: { home: number | null; draw: number | null; away: number | null }; a18_home_higher: number };
	apart: ApartRow[];
};
export const asModelCompare = (answer: (Partial<ModelCompare> & { ok?: boolean }) | null): ModelCompare | null =>
	answer?.ok === true && answer.upcoming && Array.isArray(answer.apart)
		? { start: answer.start ?? '', finished: answer.finished ?? {}, upcoming: answer.upcoming, apart: answer.apart }
		: null;

const pct = (p: number, places = 0) => `${(100 * p).toFixed(places)}%`;
// A difference in percentage points, with its sign
const points = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(100 * d).toFixed(2)}`;

// Each measure on the same finished matches: both models, and A18 minus base, marked better or
// worse for A18 (lower is better for log loss and Brier, higher for right results).
export type ScoreRow = { label: string; base: string; a18: string; gap: string; mark: 'better' | 'worse' | ''; market: string | null;
	// A18 against the bookmakers, on the matches with prices only, and A18's own figure on those
	marketGap: string | null; marketMark: 'better' | 'worse' | ''; marketNote: string };
// The bookmakers are read on the matches with stored prices, beside both models on those same
// matches, so the three are always compared on the same games.
export function scoreRows(finished: ModelCompare['finished']): { n: number; priced: number; rows: ScoreRow[] } {
	const b = finished.base, a = finished.a18, m = finished.market, bp = finished.base_priced, ap = finished.a18_priced;
	if (!b || !a || !b.n) return { n: 0, priced: 0, rows: [] };
	const priced = m && bp && ap && m.n ? m.n : 0;
	const mark = (d: number, lowerBetter: boolean) => (d === 0 ? '' : (d < 0) === lowerBetter ? 'better' : 'worse') as ScoreRow['mark'];
	const row = (label: string, key: 'log_loss' | 'brier' | 'accuracy', show: (v: number) => string, gap: (d: number) => string, lowerBetter: boolean): ScoreRow => {
		const x = b[key], y = a[key], d = y - x;
		const dm = priced ? ap![key] - m![key] : 0;
		return { label, base: show(x), a18: show(y), gap: gap(d), mark: mark(d, lowerBetter),
			market: priced ? show(m![key]) : null, marketGap: priced ? gap(dm) : null, marketMark: priced ? mark(dm, lowerBetter) : '',
			marketNote: priced && priced < Math.min(a.n, b.n) ? `A18 ${show(ap![key])} on these ${priced}` : '' };
	};
	const four = (v: number) => v.toFixed(4);
	const sign4 = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(4)}`;
	return { n: Math.min(a.n, b.n), priced, rows: [
		row('Log loss', 'log_loss', four, sign4, true),
		row('Brier', 'brier', four, sign4, true),
		row('Right result', 'accuracy', (v) => pct(v, 1), (d) => `${points(d)} pts`, false)
	] };
}

// A18's test on past matches (its change record's results from one results file): base and A18
// on each measure. No bookmakers: there are no clean stored prices for that period.
export type PastResult = { metric: string; n: number | null; baseline: number | null; after: number | null; period: [string, string] | null };
export function pastRows(results: PastResult[]): { n: number | null; period: [string, string] | null; rows: ScoreRow[] } {
	const four = (v: number) => v.toFixed(4);
	const sign4 = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d).toFixed(4)}`;
	const shown = [['Log loss', 'log_loss', four, sign4, true], ['Brier', 'brier', four, sign4, true],
		['Right result', 'accuracy', (v: number) => pct(v, 1), (d: number) => `${points(d)} pts`, false]] as const;
	const rows = shown.flatMap(([label, key, show, gap, lowerBetter]) => {
		const r = results.find((x) => x.metric === key && x.baseline != null && x.after != null);
		if (!r) return [];
		const d = r.after! - r.baseline!;
		return [{ label, base: show(r.baseline!), a18: show(r.after!), gap: gap(d), mark: (d === 0 ? '' : (d < 0) === lowerBetter ? 'better' : 'worse') as ScoreRow['mark'],
			market: null, marketGap: null, marketMark: '' as const, marketNote: '' }];
	});
	const first = results.find((x) => x.n != null);
	return { n: first?.n ?? null, period: first?.period ?? null, rows };
}

// One upcoming fixture as shown: both models' chances and expected goals
export function apartRow(r: ApartRow) {
	const hda = (p: number[]) => `${pct(p[0])} · ${pct(p[1])} · ${pct(p[2])}`;
	const xg = (p: number[]) => (p[3] != null && p[4] != null ? `${p[3].toFixed(2)}–${p[4].toFixed(2)}` : '–');
	return { fixture: r.fixture, kickoff: r.kickoff, match: `${r.home} v ${r.away}`, league: r.league, base: hda(r.base), a18: hda(r.a18),
		market: r.market ? hda(r.market) : null,
		baseXg: xg(r.base), a18Xg: xg(r.a18), gap: `${Math.abs(100 * r.gap).toFixed(1)} pts`, differ: r.differ };
}

// How far apart the two are on the fixtures to come, in words
export function upcomingSummary(u: ModelCompare['upcoming']): string {
	if (!u.n) return 'No upcoming fixtures with both models’ predictions yet.';
	const g = u.mean_gap;
	const gaps = g.home != null && g.draw != null && g.away != null
		? ` On average they are ${(100 * g.home).toFixed(1)} points apart on a home win, ${(100 * g.draw).toFixed(1)} on a draw and ${(100 * g.away).toFixed(1)} on an away win.` : '';
	return `${u.n.toLocaleString('en-GB')} upcoming fixtures. They pick a different favourite in ${u.different_favourite.toLocaleString('en-GB')} (${pct(u.different_favourite / u.n, 1)}).${gaps} A18 gives the home side more in ${pct(u.a18_home_higher / u.n)} of them.`;
}
