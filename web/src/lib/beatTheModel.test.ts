import { describe, expect, it } from 'vitest';
import { goals, matchState, nameOk, pointsFor, roundScore, type BtmMatch } from './beatTheModel.ts';

const at = Date.parse('2026-11-28T15:00:00Z');
const match = (o: Partial<BtmMatch>): BtmMatch => ({
	id: 1, kickoff: '2026-11-28T15:00:00Z', home: 40, away: 50, status: 'NS', hg: null, ag: null,
	pick: null, points: null, model: null, model_points: null, ...o
});

describe('matchState', () => {
	it('is open before kick-off until picked', () => {
		expect(matchState(match({}), at - 1)).toBe('open');
		expect(matchState(match({ pick: [2, 1] }), at - 1)).toBe('picked');
	});
	it('closes at kick-off', () => {
		expect(matchState(match({ status: '1H' }), at + 1)).toBe('missed');
		expect(matchState(match({ status: '1H', pick: [1, 1] }), at + 1)).toBe('live');
	});
	it('knows finished and called-off matches whatever the clock says', () => {
		expect(matchState(match({ status: 'FT', pick: [1, 0] }), at - 1)).toBe('done');
		expect(matchState(match({ status: 'PST' }), at + 1)).toBe('off');
	});
});

describe('goals', () => {
	it('takes whole numbers from 0 to 20 only', () => {
		expect(goals(' 2 ')).toBe(2);
		expect(goals('0')).toBe(0);
		for (const bad of ['', '-1', '1.5', '21', 'two', '100']) expect(goals(bad)).toBeNull();
	});
});

describe('pointsFor', () => {
	it('gives 3 for the exact score, 1 for the result, 0 otherwise', () => {
		expect(pointsFor([2, 1], 2, 1)).toBe(3);
		expect(pointsFor([2, 1], 3, 0)).toBe(1);
		expect(pointsFor([1, 1], 0, 0)).toBe(1);
		expect(pointsFor([1, 1], 1, 0)).toBe(0);
	});
});

describe('roundScore', () => {
	it('adds up only the marked matches', () => {
		expect(roundScore([match({ points: 3, model_points: 1 }), match({ points: 0, model_points: 1 }), match({})]))
			.toEqual({ you: 3, model: 2, marked: 2 });
	});
});

describe('nameOk', () => {
	it('matches the database rule', () => {
		expect(nameOk('Tim D')).toBe(true);
		expect(nameOk('ab')).toBe(false);
		expect(nameOk('a'.repeat(21))).toBe(false);
		expect(nameOk('bad<name>')).toBe(false);
	});
});
