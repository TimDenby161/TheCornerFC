import { describe, expect, it } from 'vitest';
import { mergeStats, pctText, type Stats } from './stats';

const part = (n: number, correct: number, o: Partial<Stats> = {}): Stats => ({
	n, live: n / 2, rated: n, correct, exact: 0.1, home_rate: 0.45, log_loss: 1, brier: 0.6, goal_error: 0.9,
	market: null, rating_avg: 3, rating_counts: [0, 0, n, 0, 0], factor_avgs: { winner: 3 }, markets: null,
	calibration: [[n, 0.05, 0.1], [0, null, null]], ...o
});

describe('mergeStats', () => {
	it('gives one competition back as it is, and nothing for none', () => {
		const a = part(10, 0.5);
		expect(mergeStats([a])).toBe(a);
		expect(mergeStats([])).toBeNull();
	});
	it('adds counts up and weights averages by matches', () => {
		const m = mergeStats([part(100, 0.6), part(300, 0.4)])!;
		expect(m.n).toBe(400);
		expect(m.live).toBe(200);
		expect(m.correct).toBeCloseTo(0.45, 9);
		expect(m.rating_counts).toEqual([0, 0, 400, 0, 0]);
		expect(m.rating_avg).toBe(3);
	});
	it('merges the market comparison over the competitions that have one, by matches with odds', () => {
		const withOdds = (n: number, ll: number) => ({ n, model_ll: ll, market_ll: ll - 0.02, model_correct: 0.5, market_correct: 0.52 });
		const m = mergeStats([part(100, 0.5, { market: withOdds(50, 1) }), part(100, 0.5, { market: withOdds(150, 0.96) }), part(100, 0.5)])!;
		expect(m.market!.n).toBe(200);
		expect(m.market!.model_ll).toBeCloseTo(0.97, 9);
		expect(mergeStats([part(1, 0.5), part(1, 0.5)])!.market).toBeNull();
	});
	it('merges each calibration band by its calls, leaving an empty band empty', () => {
		const m = mergeStats([part(100, 0.5), part(300, 0.5, { calibration: [[300, 0.07, 0.02], [0, null, null]] })])!;
		expect(m.calibration[0][0]).toBe(400);
		expect(m.calibration[0][1]).toBeCloseTo(0.065, 9);
		expect(m.calibration[0][2]).toBeCloseTo(0.04, 9);
		expect(m.calibration[1]).toEqual([0, null, null]);
	});
	it('merges the bet markets, the opening comparison over matches that have one', () => {
		const mk = (n: number, open_n: number) => ({ '1X2': { n, model_ll: 1, close_ll: 0.98, open_n, model_open_ll: open_n ? 1.02 : null, open_ll: open_n ? 1 : null } });
		const m = mergeStats([part(10, 0.5, { markets: mk(100, 40) }), part(10, 0.5, { markets: mk(50, 0) })])!;
		expect(m.markets!['1X2']).toMatchObject({ n: 150, open_n: 40 });
		expect(m.markets!['1X2'].model_open_ll).toBeCloseTo(1.02, 9);
	});
	it('writes a share as a percentage', () => {
		expect(pctText(0.5298)).toBe('53.0%');
		expect(pctText(0.337, 0)).toBe('34%');
	});
});
