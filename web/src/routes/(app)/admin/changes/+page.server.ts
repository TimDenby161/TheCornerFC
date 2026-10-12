import {
	EVALUATION_LABELS, METRIC_LABELS, NOT_SPECIFIED, TONE_WORDS, choicesFrom, counts, cumulative, deltaRows, expectedRows, filterChanges,
	headline, intervalText, monthLines, signed, tone
} from '#lib/changes.ts';
import { changesDoc } from '#lib/server/changes.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// The Model Change Tracker: the figures at the top, four charts and the list, for the choices in
// the address. The administrator's only (hooks.server.ts, and the database again for the document).
export async function load({ fetch, locals, url }) {
	const tabHead = { title: 'Model Change Tracker', ...TAB_INFO.changes };
	const doc = await changesDoc(fetch, locals.token);
	if (!doc) return { tabHead, ready: false as const };

	const ch = choicesFrom(url.searchParams, doc);
	// the measure the charts are drawn on: the one chosen, or log loss
	const metric = ch.metric === 'all' ? 'log_loss' : ch.metric;
	const shown = filterChanges(doc.changes, ch);
	const c = counts(doc.changes), cur = doc.current;
	const steps = cumulative(doc.changes), total = steps.filter((s) => s.delta != null);
	const gap = cur?.vs_market ? cur.vs_market.model_log_loss - cur.vs_market.market_log_loss : null;
	const day = (iso: string | undefined) => (iso ? iso.slice(0, 10) : '');
	const tiles: { label: string; value: string; note: string; cls?: string }[] = [
		{ label: 'Production model', value: cur?.version || 'Not recorded', note: cur?.versions?.length ? `${cur.versions.length} registered version${cur.versions.length === 1 ? '' : 's'} of it in the live record` : 'No live record yet' },
		{ label: 'Changes proposed', value: String(c.proposed), note: `${c.testing} being tested · ${c.waiting} not yet tested` },
		{ label: 'Accepted', value: String(c.accepted), note: `${c.deployed} deployed to production now` },
		{ label: 'Rejected or reverted', value: String(c.rejected + c.reverted), note: `${c.rejected} rejected · ${c.reverted} reverted · ${c.inconclusive} inconclusive` },
		{ label: 'Log loss · Brier', value: cur?.log_loss != null ? `${cur.log_loss.toFixed(4)} · ${cur.brier?.toFixed(4) ?? '–'}` : 'Not recorded', note: cur?.period ? `Predictions stored before kickoff, ${day(cur.period.from)} to ${day(cur.period.to)}` : 'The live record' },
		{ label: 'Since the earliest dated baseline', value: total.length ? signed(steps[steps.length - 1].total) : 'Not recorded', cls: total.length ? (steps[steps.length - 1].total < 0 ? 'pos' : steps[steps.length - 1].total > 0 ? 'neg' : '') : '',
			note: total.length ? `Log loss: the sum of ${total.length} deployed change${total.length === 1 ? "'s" : "s'"} own backtest${total.length === 1 ? '' : 's'}, on different samples. Earlier changes were never dated and are not counted` : 'No deployed change has a recorded backtest' },
		{ label: 'Against the bookmakers', value: gap != null ? signed(gap, 4) : 'Not recorded', cls: gap != null ? (gap < 0 ? 'pos' : gap > 0 ? 'neg' : '') : '',
			note: gap != null ? `Result log loss, model minus market, on ${cur!.vs_market!.n.toLocaleString('en-GB')} matches with stored prices in the last 12 months. ${gap > 0 ? 'Behind the market' : 'Ahead of the market'}; the registered comparison is protocol P6` : 'No matches with stored prices' },
		{ label: 'Matches in the latest evaluation', value: cur?.n != null ? cur.n.toLocaleString('en-GB') : 'Not recorded', note: 'Finished matches with a prediction stored before kickoff' }
	];

	const rows = [...shown].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : a.id < b.id ? 1 : -1)).map((x) => {
		const r = headline(x, metric) ?? x.results[0] ?? null;
		const hoped = x.expected.metrics.find((m) => m.metric === metric) ?? x.expected.metrics[0];
		return {
			id: x.id, date: x.date, title: x.title, component: x.component, stage: x.stage, status: x.status, kind: x.kind,
			expected: hoped ? `${signed(hoped.delta)}${hoped.metric !== metric ? ` ${METRIC_LABELS[hoped.metric].toLowerCase()}` : ''}` : NOT_SPECIFIED,
			result: r ? { text: signed(r.delta), tone: tone(r), word: TONE_WORDS[tone(r)], interval: intervalText(r), kind: EVALUATION_LABELS[r.evaluation], metric: METRIC_LABELS[r.metric], n: r.n } : null,
			forward: x.forward?.verdict ?? null
		};
	});
	const lineMetric = metric === 'brier' ? 'brier' : 'log_loss';
	return {
		tabHead, ready: true as const, environment: doc.environment, generated: doc.generated_at, stored: doc.stored, differs: doc.differs,
		choices: ch, statuses: doc.statuses, components: doc.components, metrics: Object.entries(METRIC_LABELS).filter(([k]) => doc.changes.some((x) => x.results.some((r) => r.metric === k))),
		tiles, rows, all: doc.changes.length, metric, metricLabel: METRIC_LABELS[metric],
		lines: monthLines(doc.series, lineMetric), lineLabel: METRIC_LABELS[lineMetric],
		deltas: deltaRows(shown, metric), expected: expectedRows(shown), steps
	};
}
