import { error } from '@sveltejs/kit';
import { EVALUATION_LABELS, METRIC_LABELS, NOT_SPECIFIED, TONE_WORDS, UNSEEN_LABELS, forwardSummary, headline, intervalText, liveStanding, liveText, markOf, notReadyNote, ready, percent, signed, tone, type Result } from '#lib/changes.ts';
import { changesDoc, liveDoc } from '#lib/server/changes.ts';
import { TAB_INFO } from '#lib/tabInfo.ts';

// One change in full: what was registered, what was expected, each result, the decision and, for
// a change deployed to production, how it has done since. The administrator's only.
export async function load({ fetch, locals, params }) {
	const [doc, running] = await Promise.all([changesDoc(fetch, locals.token), liveDoc(fetch, locals.token)]);
	const c = doc?.changes.find((x) => x.id === params.id);
	if (!doc || !c) error(404, 'No such change');
	const said = (text: string | null | undefined) => (text && text.trim() ? text : NOT_SPECIFIED);
	const places = (r: Pick<Result, 'metric'>) => (r.metric === 'mse' || r.metric === 'accuracy' || r.metric === 'roi' ? 4 : 5);
	const fwd = forwardSummary(c);
	const main = headline(c);
	const now = liveStanding(running, c.id), rec = now.record;
	const liveReady = !!rec?.ready && !c.deployed;
	return {
		tabHead: { title: 'Model Change Tracker', ...TAB_INFO.changes }, environment: doc.environment, stored: doc.stored,
		differs: doc.differs.filter((line) => line.startsWith(c.id)),
		// green on this page, as on the list, only for a change with enough evidence to implement
		ready: (!!main && ready(c, main)) || liveReady, why: liveReady ? '' : main ? notReadyNote(c, main) : '',
		// protocol P15's running record of this change on live matches
		tracking: running ? {
			text: now.text, why: now.why, start: running.start, to: running.to, generated: running.generated_at, minMatches: running.minimum.matches, minWeeks: running.minimum.weeks,
			n: rec?.n ?? 0, weeks: rec?.weeks ?? 0, gain: rec?.gain != null ? signed(rec.gain) : null,
			range: rec?.low != null && rec?.high != null ? `${signed(rec.low)} to ${signed(rec.high)}` : null,
			called: rec?.called ? `${rec.called.verdict === 'better' ? 'Proven better' : 'Proven worse'} from week ${String(rec.called.week).slice(4)} of ${String(rec.called.week).slice(0, 4)}, at ${rec.called.n.toLocaleString('en-GB')} matches` : null,
			series: (rec?.series ?? []).filter((p) => p.low != null && p.high != null).map((p) => ({ week: `${String(p.week).slice(0, 4)}-W${String(p.week).slice(4)}`, gain: p.gain, low: p.low as number, high: p.high as number, n: p.n }))
		} : null,
		change: {
			id: c.id, title: c.title, date: c.date, recorded: c.recorded, recorded_at: c.recorded_at, retrospective: c.retrospective, component: c.component,
			kind: c.kind, status: c.status, stage: c.stage, deployed: c.deployed, deployed_on: c.deployed_on, deployed_day_known: c.deployed_day_known,
			what: c.what, why: c.why, how: c.how, hypothesis: c.hypothesis, criteria: said(c.success_criteria),
			commit: said(c.code.commit), experiment: c.code.experiment, version: said(c.code.model_version),
			improves: said(c.expected.improves), betting: said(c.expected.betting), confidence: said(c.expected.confidence), evidence: said(c.expected.evidence),
			expected: c.expected.metrics.map((m) => ({ metric: METRIC_LABELS[m.metric], delta: signed(m.delta), range: m.low != null && m.high != null ? `${signed(m.low)} to ${signed(m.high)}` : null, source: m.source }))
		},
		results: c.results.map((r) => ({
			label: r.label, date: r.date, kind: EVALUATION_LABELS[r.evaluation], unseen: UNSEEN_LABELS[r.unseen], metric: METRIC_LABELS[r.metric],
			before: r.baseline != null ? r.baseline.toFixed(5) : NOT_SPECIFIED, after: r.after != null ? r.after.toFixed(5) : NOT_SPECIFIED,
			delta: signed(r.delta, places(r)), percent: percent(r), interval: intervalText(r, places(r)), n: r.n != null ? r.n.toLocaleString('en-GB') : NOT_SPECIFIED,
			period: r.period ? `${r.period[0]} to ${r.period[1]}` : NOT_SPECIFIED, tone: tone(r), mark: markOf(r === main && ready(c, r), tone(r)), word: TONE_WORDS[tone(r)], meaningful: r.meaningful, source: r.source,
			market: r.vs_market ? `${signed(r.vs_market.model_minus_market, 4)} against the market on ${r.vs_market.n.toLocaleString('en-GB')} matches${r.vs_market.note ? `. ${r.vs_market.note}` : ''}` : 'Not measured against bookmakers'
		})),
		events: c.events.map((e, i) => ({
			n: i + 1, date: e.date, month: 'date_known_to' in e && e.date_known_to === 'month', type: e.type, recorded_at: e.recorded_at ?? null,
			text: e.type === 'result' ? `${EVALUATION_LABELS[e.evaluation]}: ${e.label}, ${signed(e.delta)}`
				: e.type === 'status' ? `Status: ${e.status}${e.note ? `. ${e.note}` : ''}`
				: e.type === 'decision' ? `Decision: ${e.status}. ${e.reason}`
				: e.type === 'deployed' ? `Deployed to production${e.commit ? ` (${e.commit})` : ''}${e.note ? `. ${e.note}` : ''}`
				: e.type === 'reverted' ? `Reverted. ${e.reason}`
				: e.type === 'live_test' ? `Live test registered: protocol ${e.protocol}, on matches from ${e.start}, read once at ${e.target?.toLocaleString('en-GB')}`
				: `Correction of ${e.of === 'registration' ? 'the registration' : `event ${e.of}`}: ${e.text}`
		})),
		live: (c.live ?? []).map((t) => ({ ...t, text: liveText(t), share: Math.min(100, Math.round((100 * t.matches) / t.target)) })),
		forward: c.forward ? {
			...c.forward, expected: fwd.expected != null ? signed(fwd.expected) : NOT_SPECIFIED, backtest: fwd.backtest != null ? signed(fwd.backtest) : NOT_SPECIFIED,
			observed: fwd.observed != null ? signed(fwd.observed) : null, gap: fwd.gap != null ? signed(fwd.gap) : null
		} : null
	};
}
