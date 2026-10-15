import { describe, expect, it } from 'vitest';
import {
	NO_CHOICES, againstBaseRates, bestWaiting, choicesFrom, counts, cumulative, deltaRows, filterChanges, forwardSummary, inProduction, headline, intervalText, percent,
	gain, liveStanding, liveText, markOf, notReadyNote, ready, scale, shortId, signed, ticks, tone, type Change, type LiveDoc, type LiveRecord, type Result
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

describe('changes released inside another', () => {
	it('count as in production, never as waiting or being tested', () => {
		const idea = change('MC-0016', { status: 'Testing', released_in: 'MC-0028', results: [result({ interval: [-0.002, -0.0005] })] });
		expect(inProduction(idea)).toBe(true);
		expect(inProduction(change('MC-0001'))).toBe(false);
		expect(counts([idea]).testing).toBe(0);
		expect(bestWaiting([idea])).toBeNull();
	});
});

describe('the charts', () => {
	it('give each change with a result on the measure a row', () => {
		const rows = deltaRows([change('MC-0001'), change('MC-0002', { results: [] }), change('MC-0003', { results: [result({ metric: 'brier' })] })], 'log_loss');
		expect(rows.map((r) => r.id)).toEqual(['MC-0001']);
		expect(rows[0]).toMatchObject({ delta: -0.00076, gain: 0.00076, tone: 'better', before: 0.9936, after: 0.99284, expected: null });
	});
	it('carry the gain a change wrote down before it was tested, on the same measure, as a gain', () => {
		const hoped = { improves: 'log loss', metrics: [{ metric: 'log_loss', delta: -0.0007, source: 'DESIGN.md' }], betting: null, confidence: null, evidence: null };
		expect(deltaRows([change('MC-0001', { expected: hoped })], 'log_loss')[0].expected).toBe(0.0007);
		expect(deltaRows([change('MC-0001', { expected: hoped, results: [result({ metric: 'brier' })] })], 'brier')[0].expected).toBeNull();
	});
	it('put the best change first: proven gains, then the unproven, then the proven losses', () => {
		const rows = deltaRows([
			change('MC-0001', { results: [result({ delta: 0.0054, interval: [0.0037, 0.0069] })] }),          // proven worse
			change('MC-0002', { results: [result({ delta: -0.0074, interval: [-0.0152, 0.0003], n: 1078 })] }), // big, not proven
			change('MC-0003', { results: [result({ delta: -0.00076 })] }),                                    // proven better
			change('MC-0004', { results: [result({ delta: -0.0028, interval: [-0.0041, -0.0015] })] }),        // proven better, bigger
			change('MC-0005', { results: [result({ delta: 0.0001, interval: [-0.0001, 0.0003] })] })
		], 'log_loss');
		expect(rows.map((r) => r.id)).toEqual(['MC-0004', 'MC-0003', 'MC-0002', 'MC-0005', 'MC-0001']);
		expect(rows.map((r) => r.tone)).toEqual(['better', 'better', 'unclear', 'unclear', 'worse']);
	});
	it('mark a change ready when a test proves it better by any amount, and list those first', () => {
		const proven = (delta: number, more: Partial<Result> = {}) => result({ delta, interval: [delta - 0.0005, delta + 0.0005], ...more });
		const testing = { status: 'Testing', stage: 'Being tested' };
		expect(ready(change('x', testing), proven(-0.0028))).toBe(true);
		expect(ready(change('x', testing), proven(-0.0008))).toBe(true);                                // proven, however small
		expect(ready(change('x', testing), result({ delta: -0.0074, interval: [-0.0152, 0.0003] }))).toBe(false);   // big, not proven
		expect(ready(change('x', testing), proven(-0.0035, { evaluation: 'development' }))).toBe(false);  // the matches it was built on
		expect(ready(change('x', testing), result({ delta: -0.0035, interval: null }))).toBe(false);     // no interval, no proof
		expect(ready(change('x'), proven(-0.0028))).toBe(false);                                        // rejected
		expect(ready(change('x', { status: 'Accepted', deployed: true }), proven(-0.0028))).toBe(false); // already in production
		expect(ready(change('x', testing), proven(-0.01, { metric: 'brier' }))).toBe(true);              // any measure
		const rows = deltaRows([
			change('MC-0001', { status: 'Inconclusive', stage: 'Tested, not deployed', results: [proven(-0.0008)] }),
			change('MC-0002', { ...testing, results: [proven(-0.0028)] }),
			change('MC-0003', { status: 'Inconclusive', stage: 'Tested, not deployed', results: [proven(-0.0031, { evaluation: 'prospective' })] }),
			change('MC-0004', { results: [proven(-0.02)] })
		], 'log_loss');
		expect(rows.map((r) => [r.id, r.ready])).toEqual([['MC-0003', true], ['MC-0002', true], ['MC-0001', true], ['MC-0004', false]]);
		expect(rows.map((r) => r.readyNote)).toEqual(['Ready: proven on new matches', 'Ready on the historical test; being confirmed on new matches',
			'Ready on the historical test', 'Proven on this test, but rejected: see why on its page']);
		expect(rows.map((r) => r.mark)).toEqual(['ready', 'ready', 'ready', 'none']);
	});
	it('use green for a change that is ready and for nothing else', () => {
		expect(markOf(true, 'better')).toBe('ready');
		expect(markOf(false, 'better')).toBe('none');           // proven but rejected or deployed: no colour
		expect(markOf(false, 'unclear')).toBe('none');
		expect(markOf(false, 'worse')).toBe('worse');
		const small = result({ delta: -0.0008, interval: [-0.0014, -0.0002] });
		expect(notReadyNote(change('x', { status: 'Inconclusive' }), small)).toBe('');                  // ready, however small
		expect(notReadyNote(change('x', { status: 'Accepted', deployed: true }), small)).toBe('Already in production');
		expect(notReadyNote(change('x', { status: 'Testing' }), result({ delta: -0.003, interval: [-0.004, -0.002], evaluation: 'development' }))).toBe('Only measured on the matches it was built on');
		expect(notReadyNote(change('x', { status: 'Testing' }), result({ delta: -0.003, interval: [-0.006, 0.001] }))).toBe('');   // not proven: nothing to explain
		expect(notReadyNote(change('x', { status: 'Testing' }), result({ delta: -0.003, interval: [-0.004, -0.002] }))).toBe('');  // ready
	});
	it('carry how many live matches each registered test has reached', () => {
		const live = [{ protocol: 'P13', start: '2026-10-13', target: 9400, matches: 1312 }];
		const rows = deltaRows([change('MC-0001', { live }), change('MC-0002')], 'log_loss');
		expect(rows.find((r) => r.id === 'MC-0001')?.live).toEqual(live);
		expect(rows.find((r) => r.id === 'MC-0002')?.live).toEqual([]);
		expect(liveText(live[0])).toBe('1,312 of 9,400 (P13)');
	});
	it('add the live record: matches, gain and a call made only by the watching method', () => {
		const rec = (over: Partial<LiveRecord>): LiveRecord => ({ n: 3000, weeks: 14, gain: 0.001, low: -0.002, high: 0.004, verdict: null, called: null, ready: false, series: [], ...over });
		const live: LiveDoc = { protocol: 'P15', generated_at: 't', environment: 'production', start: '2026-10-14', planned: 6200, minimum: { matches: 500, weeks: 8 }, bar: 0.002, n: 3000, weeks: 14, to: '2027-01-20',
			changes: { 'MC-0001': rec({ gain: 0.0031, low: 0.0004, high: 0.0058, verdict: 'better', ready: true }), 'MC-0002': rec({}), 'MC-0003': rec({ gain: -0.004, low: -0.007, high: -0.001, verdict: 'worse' }),
				'MC-0004': rec({ n: 120, weeks: 1 }), 'MC-0005': rec({ gain: 0.0006, low: 0.0001, high: 0.0011, verdict: 'better' }) },
			not_run: { 'MC-0006': 'Testing chose no setting, so there is nothing to run' } };
		const open = { status: 'Inconclusive', stage: 'Tested, not deployed' };
		const unproven = result({ delta: -0.0005, interval: [-0.001, 0.0002] });
		const rows = deltaRows(['MC-0001', 'MC-0002', 'MC-0003', 'MC-0004', 'MC-0005', 'MC-0006'].map((id) => change(id, { ...open, results: [unproven] })), 'log_loss', live);
		const by = Object.fromEntries(rows.map((r) => [r.id, r]));
		expect([by['MC-0001'].ready, by['MC-0001'].mark, by['MC-0001'].readyNote]).toEqual([true, 'ready', 'Ready: proven on live matches']);
		expect([by['MC-0002'].mark, by['MC-0002'].liveText]).toEqual(['none', 'Not proven either way yet']);
		expect([by['MC-0003'].mark, by['MC-0003'].liveText]).toEqual(['worse', 'Proven worse on live matches']);
		expect(by['MC-0004'].liveText).toBe('Too early: needs 500 matches and 8 weeks');
		expect([by['MC-0005'].mark, by['MC-0005'].liveText]).toEqual(['ready', 'Proven better on live matches']);     // proven, small: green all the same
		expect([by['MC-0006'].liveText, by['MC-0006'].liveWhy]).toEqual(['Not run live', 'Testing chose no setting, so there is nothing to run']);
		expect(rows[0].id).toBe('MC-0001');                                                                      // the ready change leads
		// with no live record at all, nothing changes
		expect(deltaRows([change('MC-0001', { ...open, results: [unproven] })], 'log_loss')[0]).toMatchObject({ ready: false, liveText: 'No live record yet' });
		expect(liveStanding(live, 'MC-0001').record?.n).toBe(3000);
		// a change already in production is never marked ready by its live record
		expect(deltaRows([change('MC-0001', { status: 'Accepted', deployed: true, deployed_on: '2026-09-01', results: [unproven] })], 'log_loss', live)[0].ready).toBe(false);
		// a change with no past result is listed for its live record alone (the release P16 tracks), after those with a past
		const release = deltaRows([change('MC-0001', { status: 'Accepted', deployed: true, deployed_on: '2026-10-14', results: [] }),
			change('MC-0002', { ...open, results: [unproven] }), change('MC-0007', { results: [] })], 'log_loss', live);
		expect(release.map((r) => r.id)).toEqual(['MC-0002', 'MC-0001']);
		expect(release[1]).toMatchObject({ gain: null, n: null, ready: false, mark: 'none', readyNote: 'In production: checked on live matches', liveText: 'Proven better on live matches' });
		expect(deltaRows([change('MC-0001', { ...open, results: [] })], 'log_loss', live)[0]).toMatchObject({ ready: true, mark: 'ready', readyNote: 'Ready: proven on live matches' });
		expect(deltaRows([change('MC-0001', { ...open, results: [] })], 'brier', live)).toEqual([]);   // the live record is log loss only
	});
	it('name a change shortly and count a gain as positive whichever way the measure runs', () => {
		expect(shortId('MC-0007')).toBe('A7');
		expect(shortId('MC-0027')).toBe('A27');
		expect(gain('log_loss', -0.00076)).toBe(0.00076);
		expect(gain('accuracy', 0.01)).toBe(0.01);
		expect(gain('log_loss', 0)).toBe(0);
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
	it('place figures on a straight scale with round steps', () => {
		const x = scale([-0.004, 0.004], [0, 200]);
		expect(x(0)).toBe(100);
		expect(x(-0.004)).toBe(0);
		expect(ticks(0.97, 1.01)).toEqual([0.98, 1]);
		expect(ticks(-0.004, 0)).toEqual([-0.004, -0.003, -0.002, -0.001, 0]);
		expect(ticks(1, 1)).toEqual([1]);
	});
});

describe('how the model is doing', () => {
	const month = (m: string, source: 'live' | 'backfill', n: number, log_loss: number, home: number, draw: number, away: number) => ({ month: m, source, n, log_loss, brier: 0.59, home, draw, away });
	it('is set beside guessing the base rates of the months before the live record', () => {
		const got = againstBaseRates([month('2026-08', 'backfill', 1000, 0.99, 440, 250, 310), month('2026-09', 'backfill', 1000, 1.0, 460, 230, 310),
			month('2026-09', 'live', 200, 0.96, 100, 40, 60), month('2026-10', 'live', 600, 0.98, 270, 140, 190), month('2026-10', 'backfill', 50, 1.2, 0, 50, 0)]);
		// rates from August only, the one month wholly before the live record: a month the live record
		// shares, or a later one, is never learned from
		expect(got?.rates.map((r) => +r.toFixed(3))).toEqual([0.44, 0.25, 0.31]);
		expect(got?.n).toBe(800);
		expect(got?.model).toBeCloseTo((200 * 0.96 + 600 * 0.98) / 800, 9);
		expect(got?.base).toBeCloseTo(-(370 * Math.log(0.44) + 180 * Math.log(0.25) + 250 * Math.log(0.31)) / 800, 9);
		expect(got!.model).toBeLessThan(got!.base);
	});
	it('is not compared where the months carry no outcomes, or nothing came before', () => {
		expect(againstBaseRates([{ month: '2026-10', source: 'live', n: 600, log_loss: 0.98, brier: 0.58 }])).toBeNull();
		expect(againstBaseRates([month('2026-10', 'live', 600, 0.98, 270, 140, 190)])).toBeNull();
		expect(againstBaseRates([])).toBeNull();
	});
	it('names the largest proven gain that is not in production yet', () => {
		const best = bestWaiting([
			change('MC-0001', { status: 'Testing', stage: 'Being tested', results: [result({ delta: -0.0028, interval: [-0.0041, -0.0015] })] }),
			change('MC-0002', { status: 'Inconclusive', stage: 'Tested, not deployed', results: [result({ delta: -0.0008, interval: [-0.0014, -0.0002] })] }),
			change('MC-0003', { status: 'Testing', stage: 'Being tested', results: [result({ delta: -0.009, interval: null, evaluation: 'development' })] }),   // not a test
			change('MC-0004', { status: 'Accepted', stage: 'Deployed to production', deployed: true, deployed_on: '2026-09-01', results: [result({ delta: -0.02 })] }),
			change('MC-0005', { status: 'Rejected', results: [result({ delta: -0.03 })] })
		]);
		expect(best).toMatchObject({ id: 'MC-0001', gain: 0.0028 });
		expect(bestWaiting([change('MC-0005', { status: 'Rejected' })])).toBeNull();
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
