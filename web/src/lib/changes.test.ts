import { describe, expect, it } from 'vitest';
import {
	NO_CHOICES, choicesFrom, counts, cumulative, deltaRows, expectedRows, filterChanges, forwardSummary, headline, intervalText, monthLines, percent,
	reach, scale, signed, ticks, tone, type Change, type Result
} from './changes';

const result = (over: Partial<Result> = {}): Result => ({
	type: 'result', date: '2026-10-12', evaluation: 'backtest', unseen: 'partly', label: 'Final period', metric: 'log_loss', delta: -0.00076, n: 44383,
	period: ['2024-07-01', '2026-10-11'], baseline: 0.9936, after: 0.99284, interval: [-0.00115, -0.00039], interval_level: 0.95, vs_market: null,
	meaningful: 'Small', source: 'experiments/x/REPORT.md', ...over
});
const change = (id: string, over: Partial<Change> = {}): Change => ({
	id, title: `Change ${id}`, date: '2026-10-12', recorded: '2026-10-13', retrospective: true, component: 'Match probabilities', model: 'match', kind: 'experiment',
	what: 'w', why: 'y', how: 'h', hypothesis: 'hyp', expected: { improves: null, metrics: [], betting: null, confidence: null, evidence: null }, success_criteria: 'bar',
	code: { commit: null, experiment: null, model_version: null }, recorded_at: null, status: 'Rejected', stage: 'Tested and rejected', deployed: false,
	deployed_on: null, deployed_day_known: null, reverted_on: null, decided_on: '2026-10-12', events: [], results: [result()], forward: null, ...over
});

describe('what a result shows', () => {
	it('is better or worse only when its interval leaves zero out', () => {
		expect(tone(result())).toBe('better');
		expect(tone(result({ delta: 0.0054, interval: [0.0037, 0.0069] }))).toBe('worse');
		expect(tone(result({ delta: -0.00024, interval: [-0.00065, 0.00024] }))).toBe('unclear');
		expect(tone(result({ delta: -0.00113, interval: null }))).toBe('unclear');
	});
	it('knows a rise in accuracy or return is the improvement', () => {
		expect(tone(result({ metric: 'accuracy', delta: 0.01, interval: [0.002, 0.02] }))).toBe('better');
		expect(tone(result({ metric: 'roi', delta: -0.05, interval: [-0.09, -0.01] }))).toBe('worse');
	});
	it('is written with its sign, as a share of the figure before, and with its interval', () => {
		expect(signed(-0.00076)).toBe('−0.00076');
		expect(signed(0.0054)).toBe('+0.00540');
		expect(signed(0)).toBe('0.00000');
		expect(signed(-0.0000001)).toBe('0.00000');
		expect(percent(result())).toBe('−0.08%');
		expect(percent(result({ baseline: null }))).toBeNull();
		expect(intervalText(result())).toBe('−0.00115 to −0.00039 (95%)');
		expect(intervalText(result({ interval_level: 0.996 }))).toBe('−0.00115 to −0.00039 (99.6%)');
		expect(intervalText(result({ interval: null }))).toBeNull();
	});
	it('speaks through the strongest evidence a change has on a measure', () => {
		const c = change('MC-0001', { results: [result({ evaluation: 'development', delta: -0.003, label: 'dev' }), result({ label: 'test' }), result({ evaluation: 'prospective', delta: -0.001, label: 'live' }), result({ metric: 'brier', delta: -0.0004 })] });
		expect(headline(c)?.label).toBe('live');
		expect(headline(c, 'brier')?.delta).toBe(-0.0004);
		expect(headline(c, 'rps')).toBeNull();
	});
});

describe('choices and counts', () => {
	const doc = { statuses: ['Proposed', 'Testing', 'Accepted', 'Rejected', 'Reverted', 'Inconclusive'], components: ['Club rank', 'Match probabilities'] };
	const all = [
		change('MC-0001', { status: 'Accepted', stage: 'Deployed to production', deployed: true, deployed_on: '2026-09-01', kind: 'production change', date: '2026-09-01', component: 'Club rank' }),
		change('MC-0002'), change('MC-0003', { status: 'Testing', stage: 'Being tested', results: [result({ metric: 'brier' })] }),
		change('MC-0004', { status: 'Accepted', stage: 'Tested, not deployed' }), change('MC-0005', { status: 'Reverted', stage: 'Reverted', date: '2026-11-02' })
	];
	it('keep only what the document knows, from the address', () => {
		expect(choicesFrom(new URLSearchParams('status=Rejected&component=Club%20rank&metric=brier&from=2026-10-01&to=2026-10-31'), doc))
			.toEqual({ status: 'Rejected', component: 'Club rank', metric: 'brier', from: '2026-10-01', to: '2026-10-31' });
		expect(choicesFrom(new URLSearchParams('status=Deployed&component=x&metric=<script>&from=yesterday&to=2026-13'), doc)).toEqual(NO_CHOICES);
	});
	it('narrow the list by status, part of the model, measure and date', () => {
		const ids = (ch: Partial<typeof NO_CHOICES>) => filterChanges(all, { ...NO_CHOICES, ...ch }).map((c) => c.id);
		expect(ids({})).toHaveLength(5);
		expect(ids({ status: 'Accepted' })).toEqual(['MC-0001', 'MC-0004']);
		expect(ids({ component: 'Club rank' })).toEqual(['MC-0001']);
		expect(ids({ metric: 'brier' })).toEqual(['MC-0003']);
		expect(ids({ from: '2026-10-01', to: '2026-10-31' })).toEqual(['MC-0002', 'MC-0003', 'MC-0004']);
	});
	it('count an accepted change and a deployed one apart', () => {
		expect(counts(all)).toMatchObject({ proposed: 5, accepted: 2, deployed: 1, rejected: 1, reverted: 1, testing: 1 });
	});
});

describe('the charts', () => {
	it('give each change with a result on the measure a row', () => {
		const rows = deltaRows([change('MC-0001'), change('MC-0002', { results: [] }), change('MC-0003', { results: [result({ metric: 'brier' })] })], 'log_loss');
		expect(rows.map((r) => r.id)).toEqual(['MC-0001']);
		expect(rows[0]).toMatchObject({ delta: -0.00076, tone: 'better', before: 0.9936, after: 0.99284 });
	});
	it('set an expectation beside a test, never beside the figure a change was built on', () => {
		const hoped = { improves: 'log loss', metrics: [{ metric: 'log_loss', delta: -0.0007, low: -0.0011, high: -0.0003, source: 'DESIGN.md' }], betting: null, confidence: null, evidence: null };
		const rows = expectedRows([
			change('MC-0001', { expected: hoped }),
			change('MC-0002', { expected: hoped, results: [result({ evaluation: 'development', delta: -0.0035 })] }),
			change('MC-0003')
		]);
		expect(rows.map((r) => r.id)).toEqual(['MC-0001', 'MC-0002']);
		expect(rows[0]).toMatchObject({ expected: -0.0007, range: [-0.0011, -0.0003], actual: -0.00076, actualFrom: 'backtest' });
		expect(rows[0].gap).toBeCloseTo(-0.00006, 6);
		expect(rows[1]).toMatchObject({ actual: null, gap: null });
	});
	it('add up only the changes that are in production, in the order they went live', () => {
		const steps = cumulative([
			change('MC-0003', { deployed: true, deployed_on: '2026-11-01', results: [result({ delta: -0.002 })] }),
			change('MC-0001', { deployed: true, deployed_on: '2026-09-01', results: [result({ delta: -0.00113, interval: null })] }),
			change('MC-0002'),                                                                               // an experiment: never in the total
			change('MC-0004', { deployed: true, deployed_on: '2026-09-25', model: 'betting', results: [] }),   // another model
			change('MC-0005', { deployed: true, deployed_on: '2026-12-01', results: [result({ evaluation: 'development', delta: -0.01 })] })
		]);
		expect(steps.map((s) => s.id)).toEqual(['MC-0001', 'MC-0003', 'MC-0005']);
		expect(steps.map((s) => s.delta)).toEqual([-0.00113, -0.002, null]);
		expect(steps[2].total).toBeCloseTo(-0.00313, 6);
	});
	it('keep the stored record and the reconstructed history as separate lines, without thin months', () => {
		const lines = monthLines([
			{ month: '2026-08', source: 'backfill', n: 1500, log_loss: 0.99, brier: 0.59 }, { month: '2026-09', source: 'backfill', n: 900, log_loss: 1.0, brier: 0.6 },
			{ month: '2026-09', source: 'live', n: 150, log_loss: 0.9, brier: 0.5 }, { month: '2026-10', source: 'live', n: 600, log_loss: 0.97, brier: 0.58 }
		], 'log_loss');
		expect(lines.map((l) => [l.source, l.points.map((p) => p.month)])).toEqual([['backfill', ['2026-08', '2026-09']], ['live', ['2026-10']]]);
	});
	it('place figures on a straight scale with round steps', () => {
		const x = scale([-0.004, 0.004], [0, 200]);
		expect(x(0)).toBe(100);
		expect(x(-0.004)).toBe(0);
		expect(ticks(0.97, 1.01)).toEqual([0.98, 1]);
		expect(ticks(-0.004, 0)).toEqual([-0.004, -0.003, -0.002, -0.001, 0]);
		expect(ticks(1, 1)).toEqual([1]);
		expect(reach([-0.003, 0.001, null, undefined])).toBe(0.003);
		expect(reach([])).toBe(1);
	});
});

describe('the forward record', () => {
	const win = (gap: number, n = 2000) => ({ n, log_loss: 0.98, brier: 0.58, vs_market: { n: 1500, model_log_loss: 0.98, market_log_loss: 0.98 - gap, model_minus_market: gap } });
	it('measures what has been seen since as the move in the distance from the market', () => {
		const c = change('MC-0001', {
			deployed: true, deployed_on: '2026-11-01', expected: { improves: null, metrics: [{ metric: 'log_loss', delta: -0.003, source: 'x' }], betting: null, confidence: null, evidence: null },
			forward: { from: '2026-11-01', to: '2027-02-01', after: win(0.017), before: win(0.019), verdict: 'Still appears beneficial', why: 'Closer to the market.', deployed_with: [] }
		});
		const f = forwardSummary(c);
		expect(f.expected).toBe(-0.003);
		expect(f.backtest).toBe(-0.00076);
		expect(f.observed).toBeCloseTo(-0.002, 6);
		expect(f.gap).toBeCloseTo(0.001, 6);
		expect(f.matches).toBe(2000);
	});
	it('says nothing was observed where one side has no prices, and nothing was expected where no number was written', () => {
		const c = change('MC-0002', { forward: { from: null, to: null, after: null, before: null, verdict: 'Cannot be judged', why: 'No day.', deployed_with: [] } });
		expect(forwardSummary(c)).toMatchObject({ expected: null, observed: null, gap: null, matches: 0, verdict: 'Cannot be judged' });
	});
});
