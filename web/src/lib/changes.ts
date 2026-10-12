// The Model Change Tracker's sums: what a result shows, which changes a set of choices keeps, and
// the rows and points its charts draw. The document is the administrator's (admin_docs
// "model_changes", built by thecornerfc/evidence/model_changes.py); nothing here is public.

export type ExpectedMetric = { metric: string; delta: number; low?: number; high?: number; source: string };
export type Expected = { improves: string | null; metrics: ExpectedMetric[]; betting: string | null; confidence: string | null; evidence: string | null };
export type MarketGap = { n: number; model_minus_market: number; note?: string };
export type Result = {
	type: 'result'; date: string; evaluation: 'development' | 'backtest' | 'prospective'; unseen: 'yes' | 'partly' | 'no'; label: string; metric: string;
	delta: number; n: number | null; period: [string, string] | null; baseline: number | null; after: number | null;
	interval: [number, number] | null; interval_level: number | null; vs_market: MarketGap | null; meaningful: string; source: string;
	experimental?: boolean; recorded_at?: string | null;
};
export type ChangeEvent = Result | { type: 'status' | 'decision' | 'deployed' | 'reverted' | 'correction'; date: string; date_known_to?: 'day' | 'month'; status?: string; note?: string; reason?: string; commit?: string | null; model_version?: string | null; of?: 'registration' | number; text?: string; recorded_at?: string | null };
export type Window = { n: number; log_loss: number | null; brier: number | null; vs_market: { n: number; model_log_loss: number; market_log_loss: number; model_minus_market: number } | null };
export type Forward = { from: string | null; to: string | null; after: Window | null; before: Window | null; verdict: string; why: string; deployed_with: string[] };
export type Change = {
	id: string; title: string; date: string; recorded: string; retrospective: boolean; component: string; model: string; kind: 'experiment' | 'production change';
	what: string; why: string; how: string; hypothesis: string; expected: Expected; success_criteria: string;
	code: { commit: string | null; experiment: string | null; model_version: string | null };
	recorded_at: string | null; status: string; stage: string; deployed: boolean; deployed_on: string | null; deployed_day_known: boolean | null;
	reverted_on: string | null; decided_on: string | null; events: ChangeEvent[]; results: Result[]; forward: Forward | null;
};
export type SeriesPoint = { month: string; source: 'live' | 'backfill'; n: number; log_loss: number; brier: number };
export type Current = { version: string | null; versions: { name: string; n: number }[]; n: number | null; period: { from: string; to: string } | null; log_loss: number | null; brier: number | null; accuracy: number | null; vs_market: { n: number; model_log_loss: number; market_log_loss: number } | null };
export type ChangesDoc = { generated_at: string; environment: string | null; stored: boolean; differs: string[]; not_specified: string; statuses: string[]; components: string[]; current: Current | null; series: SeriesPoint[]; changes: Change[] };

export const NOT_SPECIFIED = 'Not specified';
export const METRIC_LABELS: Record<string, string> = {
	log_loss: 'Log loss', brier: 'Brier score', rps: 'Ranked probability score', accuracy: 'Right result', calibration_error: 'Calibration error',
	goal_markets_log_loss: 'Goal markets log loss', mse: 'Squared error', mae: 'Absolute error', roi: 'Return', other: 'Other measure'
};
// A lower figure is the better one for every measure but these two
const HIGHER_IS_BETTER = new Set(['accuracy', 'roi']);
export const better = (metric: string, delta: number) => (HIGHER_IS_BETTER.has(metric) ? delta > 0 : delta < 0);

// What a result shows. "better" and "worse" are said only when its interval leaves zero out: a
// figure with no interval, or one whose interval crosses zero, is "unclear" whatever its sign.
export type Tone = 'better' | 'worse' | 'unclear';
export function tone(r: Pick<Result, 'metric' | 'delta' | 'interval'>): Tone {
	if (!r.interval) return 'unclear';
	const [lo, hi] = r.interval;
	if (lo <= 0 && hi >= 0) return 'unclear';
	return better(r.metric, r.delta) ? 'better' : 'worse';
}
export const TONE_WORDS: Record<Tone, string> = { better: 'Better', worse: 'Worse', unclear: 'Unclear' };

// A change in a measure, signed, to the places these measures move in
export function signed(value: number, places = 5): string {
	const text = Math.abs(value).toFixed(places);
	return Number(text) === 0 ? text : `${value < 0 ? '−' : '+'}${text}`;
}
// The change as a share of the figure before it, where that figure was recorded
export function percent(r: Pick<Result, 'delta' | 'baseline'>): string | null {
	if (r.baseline == null || r.baseline === 0) return null;
	const p = (100 * r.delta) / r.baseline;
	return `${p < 0 ? '−' : '+'}${Math.abs(p).toFixed(2)}%`;
}
export const intervalText = (r: Pick<Result, 'interval' | 'interval_level'>, places = 5) =>
	r.interval ? `${signed(r.interval[0], places)} to ${signed(r.interval[1], places)}${r.interval_level ? ` (${+(100 * r.interval_level).toFixed(1)}%)` : ''}` : null;

// How far a kind of evidence can be trusted, strongest first: matches no one had seen when the
// change was fixed, then a historical test, then the figures it was built on.
const RANK: Record<string, number> = { prospective: 0, backtest: 1, development: 2 };
export const EVALUATION_LABELS: Record<string, string> = { prospective: 'Prospective test', backtest: 'Historical backtest', development: 'Development figure' };
export const UNSEEN_LABELS: Record<string, string> = { yes: 'Matches the change had not seen', partly: 'Held out, but looked at before', no: 'The matches it was built on' };

// The one result that speaks for a change on a measure: the strongest kind of evidence it has,
// and of those the first recorded. null where it has none on that measure.
export function headline(c: Change, metric = 'log_loss'): Result | null {
	const on = c.results.filter((r) => r.metric === metric);
	return on.length ? [...on].sort((a, b) => RANK[a.evaluation] - RANK[b.evaluation])[0] : null;
}

export type Choices = { status: string; component: string; metric: string; from: string; to: string };
export const NO_CHOICES: Choices = { status: 'all', component: 'all', metric: 'all', from: '', to: '' };
const DAY = /^\d{4}-\d{2}-\d{2}$/;
// The choices an address carries, each kept only where it is one the document knows
export function choicesFrom(q: URLSearchParams, doc: Pick<ChangesDoc, 'statuses' | 'components'>): Choices {
	const one = (k: string, ok: string[]) => (ok.includes(q.get(k) || '') ? q.get(k)! : 'all');
	const day = (k: string) => (DAY.test(q.get(k) || '') ? q.get(k)! : '');
	return { status: one('status', doc.statuses), component: one('component', doc.components), metric: one('metric', Object.keys(METRIC_LABELS)), from: day('from'), to: day('to') };
}
export function filterChanges(changes: Change[], ch: Choices): Change[] {
	return changes.filter((c) =>
		(ch.status === 'all' || c.status === ch.status) && (ch.component === 'all' || c.component === ch.component) &&
		(ch.metric === 'all' || c.results.some((r) => r.metric === ch.metric) || c.expected.metrics.some((m) => m.metric === ch.metric)) &&
		(!ch.from || c.date >= ch.from) && (!ch.to || c.date <= ch.to));
}

// The counts at the top of the page. "Accepted" is a decision; "deployed" is a change that is
// in production now. They are counted apart so that one is never read as the other.
export function counts(changes: Change[]) {
	const n = (f: (c: Change) => boolean) => changes.filter(f).length;
	return {
		proposed: changes.length, accepted: n((c) => c.status === 'Accepted'), deployed: n((c) => c.deployed),
		rejected: n((c) => c.status === 'Rejected'), reverted: n((c) => c.status === 'Reverted'),
		testing: n((c) => c.status === 'Testing'), inconclusive: n((c) => c.status === 'Inconclusive'), waiting: n((c) => c.status === 'Proposed')
	};
}

// Chart 2, before and after each change: a row for each change with a result on the measure
export type DeltaRow = { id: string; title: string; stage: string; evaluation: string; delta: number; interval: [number, number] | null; tone: Tone; before: number | null; after: number | null; n: number | null };
export function deltaRows(changes: Change[], metric: string): DeltaRow[] {
	return changes.flatMap((c) => {
		const r = headline(c, metric);
		return r ? [{ id: c.id, title: c.title, stage: c.stage, evaluation: r.evaluation, delta: r.delta, interval: r.interval, tone: tone(r), before: r.baseline, after: r.after, n: r.n }] : [];
	});
}

// Chart 3, expected against actual: every change that recorded a number beforehand, with what a
// test (never a development figure) then showed on the same measure, or null while there is none
export type ExpectedRow = { id: string; title: string; metric: string; expected: number; range: [number, number] | null; actual: number | null; actualFrom: string | null; gap: number | null };
export function expectedRows(changes: Change[]): ExpectedRow[] {
	return changes.flatMap((c) => c.expected.metrics.map((m) => {
		const tested = c.results.filter((r) => r.metric === m.metric && r.evaluation !== 'development').sort((a, b) => RANK[a.evaluation] - RANK[b.evaluation])[0];
		return { id: c.id, title: c.title, metric: m.metric, expected: m.delta, range: m.low != null && m.high != null ? [m.low, m.high] as [number, number] : null,
			actual: tested ? tested.delta : null, actualFrom: tested ? tested.evaluation : null, gap: tested ? tested.delta - m.delta : null };
	}));
}

// Chart 4, the running total across the versions that went to production: each deployed change's
// own backtest gain on the measure, added in the order they went live. The samples differ from
// change to change, so the total is a sum of separate tests, not one measurement.
export type Step = { id: string; title: string; on: string; delta: number | null; total: number };
export function cumulative(changes: Change[], metric = 'log_loss', model = 'match'): Step[] {
	let total = 0;
	return changes.filter((c) => c.deployed && c.model === model).sort((a, b) => (a.deployed_on! < b.deployed_on! ? -1 : a.deployed_on! > b.deployed_on! ? 1 : a.id < b.id ? -1 : 1)).map((c) => {
		const r = headline(c, metric);
		const delta = r && r.evaluation !== 'development' ? r.delta : null;
		total += delta ?? 0;
		return { id: c.id, title: c.title, on: c.deployed_on!, delta, total };
	});
}

// Chart 1, the model's results by month on a measure: one line for the predictions stored before
// kickoff and one for the reconstructed history, which is today's code replayed and so not a
// record of what any earlier version said. A month with under `floor` matches is left out.
export type Line = { source: 'live' | 'backfill'; points: { month: string; value: number; n: number }[] };
export function monthLines(series: SeriesPoint[], metric: 'log_loss' | 'brier', floor = 200): Line[] {
	return (['backfill', 'live'] as const).map((source) => ({ source, points: series.filter((s) => s.source === source && s.n >= floor).map((s) => ({ month: s.month, value: s[metric], n: s.n })) })).filter((l) => l.points.length);
}

// Where figures sit on a chart: a straight scale from a domain to a range, and round steps for
// its axis. Positions are written as SVG attributes (the security policy allows no inline styles).
export function scale(domain: [number, number], range: [number, number]) {
	const span = domain[1] - domain[0] || 1;
	return (v: number) => range[0] + ((v - domain[0]) / span) * (range[1] - range[0]);
}
export function ticks(lo: number, hi: number, about = 4): number[] {
	const span = hi - lo;
	if (!(span > 0)) return [lo];
	const raw = span / about, mag = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
	const out: number[] = [];
	for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
	return out;
}
// The widest a set of changes and their intervals reach either side of zero, for a shared scale
export function reach(values: (number | null | undefined)[]): number {
	return Math.max(0, ...values.filter((v): v is number => v != null).map(Math.abs)) || 1;
}

// The forward record in a sentence each: what was expected, what the backtest gave, what has
// been seen since, and how far the last is from the first
export function forwardSummary(c: Change, metric = 'log_loss') {
	const expected = c.expected.metrics.find((m) => m.metric === metric)?.delta ?? null;
	const tested = c.results.filter((r) => r.metric === metric && r.evaluation === 'backtest')[0]?.delta ?? null;
	const f = c.forward;
	const observed = f?.after?.vs_market && f.before?.vs_market ? f.after.vs_market.model_minus_market - f.before.vs_market.model_minus_market : null;
	return { expected, backtest: tested, observed, matches: f?.after?.n ?? 0, gap: observed != null && expected != null ? observed - expected : null, verdict: f?.verdict ?? null, why: f?.why ?? null };
}
