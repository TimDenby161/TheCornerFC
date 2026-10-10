import { describe, expect, it } from 'vitest';
import { averageRank, markPredicted, spots, withAbility, type Starter, type XiRow } from './lineups';

const starter = (id: number, label: string): Starter => ({ id, name: `A. Player${id}`, label, rank: 70 });
describe('markPredicted', () => {
	it('counts the starters the model had, and marks each one', () => {
		const xi = [starter(1, 'GK'), starter(2, 'CB'), starter(3, 'ST')];
		const hits = markPredicted(xi, [[1, 'A', 'GK', 80], [2, 'B', 'CB', 75], [9, 'C', 'ST', 70]]);
		expect(hits).toBe(2);
		expect(xi.map((c) => c.predicted)).toEqual([true, true, false]);
	});
	it('pairs a miss with the pick who didn\'t start: same position, then group, then line, then anyone', () => {
		const xi = [starter(1, 'LB'), starter(2, 'CM'), starter(3, 'ST'), starter(4, 'GK')];
		const predicted: XiRow[] = [[11, 'Same', 'ST', 60], [12, 'Group', 'RB', 61], [13, 'Line', 'AM', 62], [14, 'Anyone', 'CB', 63]];
		expect(markPredicted(xi, predicted)).toBe(0);
		expect(xi.map((c) => c.instead?.[1])).toEqual(['Group', 'Line', 'Same', 'Anyone']);
	});
	it('gives a miss no pick when every pick started', () => {
		const xi = [starter(1, 'GK'), starter(2, 'CB')];
		markPredicted(xi, [[1, 'A', 'GK', 80]]);
		expect(xi[1].predicted).toBe(false);
		expect(xi[1].instead).toBeUndefined();
	});
});

describe('spots', () => {
	it('says what happened to each starter in words', () => {
		const xi = [starter(1, 'GK'), starter(3, 'ST')];
		markPredicted(xi, [[1, 'A', 'GK', 80], [9, 'J. Other', 'ST', 71.26]]);
		const [gk, st] = spots(xi).sort((a, b) => a.y - b.y);
		expect(gk.tip).toBe('A. Player1 · GK · rank 70.0 · predicted to start');
		expect(st.tip).toBe('A. Player3 · ST · rank 70.0 · not predicted; the model picked J. Other (rank 71.3)');
		expect(st.instead).toEqual({ name: 'Other', rank: 71.26 });
		expect(gk.name).toBe('Player1');
	});
	it('leaves ranks out for a national side', () => {
		expect(spots([{ id: 1, name: 'A. Keeper', label: 'GK', rank: null }], false)[0].tip).toBe('A. Keeper · GK');
	});
	it('shows a predicted XI\'s chance and minutes', () => {
		expect(spots([{ id: 1, name: 'A. Keeper', label: 'GK', rank: 80.5, chance: 97.6, mins: 88 }])[0]).toMatchObject({ chance: 98, mins: 88, predicted: null, tip: 'A. Keeper · GK · rank 80.5 · 98% to start · 88′ expected' });
	});
});

describe('withAbility', () => {
	it('swaps each stored rank for the player\'s Ability, and leaves none where he has none', () => {
		const rows: XiRow[] = [[1, 'A', 'AM', 94.2], [2, 'B', 'ST', 64], [3, 'C', 'GK', 87]];
		expect(withAbility(rows, new Map([[1, 84.3], [2, null]]))).toEqual([[1, 'A', 'AM', 84.3], [2, 'B', 'ST', null], [3, 'C', 'GK', null]]);
	});
});

describe('averageRank', () => {
	it('averages the ranks there are, to a whole number', () => {
		expect(averageRank([84.3, 70, null, 77.2])).toBe(77);
		expect(averageRank([null])).toBeNull();
		expect(averageRank([])).toBeNull();
	});
});
