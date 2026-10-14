import {
	EVALUATION_LABELS, METRIC_LABELS, NOT_SPECIFIED, TONE_WORDS, againstBaseRates, bestWaiting, choicesFrom, counts, cumulative, deltaRows,
	filterChanges, headline, intervalText, markOf, monthLines, ready, shortId, signed, tone
} from '#lib/changes.ts';
import { fail } from '@sveltejs/kit';
import { matchModel, matchModelCompare, switchMatchModel } from '#lib/server/admin.ts';
import { changesDoc, liveDoc } from '#lib/server/changes.ts';
import { apartRow, isMatchModel, scoreRows, upcomingSummary } from '#lib/matchModels.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// The Model Change Tracker: the figures at the top, three charts and the list, for the choices in
// the address. The administrator's only (hooks.server.ts, and the database again for the document).
const CHALLENGER = 'MC-0029';

export async function load({ fetch, locals, url }) {
	const tabHead = { title: 'Model Change Tracker', ...TAB_INFO.changes };
	const [doc, live, model, compare] = await Promise.all([changesDoc(fetch, locals.token), liveDoc(fetch, locals.token), matchModel(fetch, locals.token), matchModelCompare(fetch, locals.token)]);
	if (!doc) return { tabHead, ready: false as const };

	const ch = choicesFrom(url.searchParams, doc);
	// the measure the charts are drawn on: the one chosen, or log loss
	const metric = ch.metric === 'all' ? 'log_loss' : ch.metric;
	const shown = filterChanges(doc.changes, ch);
	const c = counts(doc.changes), cur = doc.current;
	const steps = cumulative(doc.changes), total = steps.filter((s) => s.delta != null);
	const gap = cur?.vs_market ? cur.vs_market.model_log_loss - cur.vs_market.market_log_loss : null;
	const day = (iso: string | undefined) => (iso ? iso.slice(0, 10) : '');
	// How the model is doing now, how it has got better and how it compares with other
	// forecasters. (How many changes were accepted or rejected is in the list below.)
	const base = againstBaseRates(doc.series), next = bestWaiting(doc.changes);
	const pos = (v: number) => (v < 0 ? 'pos' : v > 0 ? 'neg' : '');
	const tiles: { label: string; value: string; note: string; cls?: string }[] = [
		{ label: 'Production model', value: cur?.version || 'Not recorded', note: `${c.proposed} changes proposed · ${c.deployed} in production · ${c.testing} being tested` },
		{ label: 'Log loss · Brier now', value: cur?.log_loss != null ? `${cur.log_loss.toFixed(4)} · ${cur.brier?.toFixed(4) ?? '–'}` : 'Not recorded', note: cur?.period ? `Predictions stored before kickoff, ${day(cur.period.from)} to ${day(cur.period.to)}. Lower is better` : 'The live record' },
		{ label: 'Right result now', value: cur?.accuracy != null ? `${(100 * cur.accuracy).toFixed(1)}%` : 'Not recorded', note: cur?.n != null ? `The outcome the model made most likely happened, on ${cur.n.toLocaleString('en-GB')} matches with a prediction stored before kickoff` : 'No live record yet' },
		{ label: 'Against guessing the base rates', value: base ? signed(base.model - base.base, 4) : 'Not recorded', cls: base ? pos(base.model - base.base) : '',
			note: base ? `Log loss ${base.model.toFixed(4)} against ${base.base.toFixed(4)} for giving every match ${(100 * base.rates[0]).toFixed(0)}% / ${(100 * base.rates[1]).toFixed(0)}% / ${(100 * base.rates[2]).toFixed(0)}%, on ${base.n.toLocaleString('en-GB')} live matches. Minus means the model is better` : 'Needs a live record and the months before it' },
		{ label: 'Against the bookmakers', value: gap != null ? signed(gap, 4) : 'Not recorded', cls: gap != null ? pos(gap) : '',
			note: gap != null ? `Result log loss, model minus market, on ${cur!.vs_market!.n.toLocaleString('en-GB')} matches with stored prices in the last 12 months. ${gap > 0 ? 'Behind the market' : 'Ahead of the market'}; the registered comparison is protocol P6` : 'No matches with stored prices' },
		{ label: 'Gained since the earliest dated version', value: total.length ? signed(-steps[steps.length - 1].total) : 'Not recorded', cls: total.length ? pos(steps[steps.length - 1].total) : '',
			note: total.length ? `Log loss: the sum of ${total.length} deployed change${total.length === 1 ? "'s" : "s'"} own backtest${total.length === 1 ? '' : 's'}, on different samples. Plus is an improvement. Earlier changes were never dated and are not counted` : 'No deployed change has a recorded backtest' },
		{ label: 'Best proven gain not yet in production', value: next ? signed(next.gain) : 'None yet', cls: next ? 'pos' : '',
			note: next ? `${shortId(next.id)} · ${next.title}${next.n ? `, on ${next.n.toLocaleString('en-GB')} matches` : ''}. ${next.stage}: a historical test, not yet confirmed on new matches` : 'No change outside production has a proven gain' },
		{ label: 'Matches in the latest evaluation', value: cur?.n != null ? cur.n.toLocaleString('en-GB') : 'Not recorded', note: 'Finished matches with a prediction stored before kickoff' }
	];

	const rows = [...shown].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : a.id < b.id ? 1 : -1)).map((x) => {
		const r = headline(x, metric) ?? x.results[0] ?? null;
		const hoped = x.expected.metrics.find((m) => m.metric === metric) ?? x.expected.metrics[0];
		return {
			id: x.id, date: x.date, title: x.title, component: x.component, stage: x.stage, status: x.status, kind: x.kind,
			expected: hoped ? `${signed(hoped.delta)}${hoped.metric !== metric ? ` ${METRIC_LABELS[hoped.metric].toLowerCase()}` : ''}` : NOT_SPECIFIED,
			result: r ? { text: signed(r.delta), tone: tone(r), mark: markOf(ready(x, r), tone(r)), word: ready(x, r) ? 'Ready to implement' : tone(r) === 'better' ? 'Proven, not ready' : TONE_WORDS[tone(r)], interval: intervalText(r), kind: EVALUATION_LABELS[r.evaluation], metric: METRIC_LABELS[r.metric], n: r.n } : null,
			forward: x.forward?.verdict ?? null
		};
	});
	const lineMetric = metric === 'brier' ? 'brier' : 'log_loss';
	// The two match models side by side, above the switch: A18's test on past matches (its change
	// record), the head-to-head on live matches (P18, from the Live tracking job), each measure
	// on the same finished matches, and where they part on the fixtures to come.
	const challenger = doc.changes.find((x) => x.id === CHALLENGER);
	const past = challenger?.expected.metrics.find((m) => m.metric === 'log_loss') ?? null;
	const p18 = live?.changes[CHALLENGER] ?? null;
	const versus = model ? {
		past: past ? { delta: signed(past.delta, 4), low: past.low != null ? signed(past.low, 4) : null, high: past.high != null ? signed(past.high, 4) : null, source: past.source } : null,
		// P18 records A18's gain (plus is better); shown here as A18 minus base, like everything else on the card
		p18: p18 ? { n: p18.n, weeks: p18.weeks, delta: p18.gain != null ? signed(-p18.gain, 4) : null, low: p18.high != null ? signed(-p18.high, 4) : null, high: p18.low != null ? signed(-p18.low, 4) : null,
			verdict: p18.verdict, generated: live!.generated_at, matches: live!.minimum.matches, minWeeks: live!.minimum.weeks } : null,
		target: challenger?.live?.find((t) => t.protocol === 'P18')?.target ?? (challenger?.events ?? []).flatMap((e) => (e.type === 'live_test' && 'target' in e && e.target ? [e.target] : []))[0] ?? null,
		scores: compare ? scoreRows(compare.finished) : null, start: compare?.start ?? null,
		upcoming: compare ? upcomingSummary(compare.upcoming) : null,
		apart: compare ? compare.apart.map(apartRow) : []
	} : null;
	return {
		tabHead, ready: true as const, environment: doc.environment, generated: doc.generated_at, stored: doc.stored, differs: doc.differs,
		choices: ch, statuses: doc.statuses, components: doc.components, metrics: Object.entries(METRIC_LABELS).filter(([k]) => doc.changes.some((x) => x.results.some((r) => r.metric === k))),
		tiles, rows, all: doc.changes.length, metric, metricLabel: METRIC_LABELS[metric],
		lines: monthLines(doc.series, lineMetric), lineLabel: METRIC_LABELS[lineMetric],
		// Table 2 is for deciding what to add, so changes already in production are left out of it
		deltas: deltaRows(shown.filter((x) => !x.deployed), metric, live), steps,
		model, versus,
		live: live ? { n: live.n, weeks: live.weeks, start: live.start, to: live.to, generated: live.generated_at, tracked: Object.keys(live.changes).length, protocol: live.protocol, matches: live.minimum.matches, minWeeks: live.minimum.weeks } : null
	};
}

export const actions = {
	// The switch: which match model the site and the paper bets use, from the next run of the
	// predictions. The database checks the caller is an administrator and logs every switch.
	switch: async ({ request, fetch, locals }) => {
		const live = (await request.formData()).get('live');
		if (!isMatchModel(live)) return fail(400, { message: 'That is not one of the two models.' });
		const model = await switchMatchModel(fetch, locals.token, live);
		if (!model) return fail(403, { message: 'The switch was refused, or is not there yet.' });
		return { switched: model.live };
	}
};
