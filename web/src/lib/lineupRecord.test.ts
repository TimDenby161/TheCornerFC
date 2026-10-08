import { describe, expect, it } from 'vitest';
import { clubExtremes, historySummary, liveRows, liveSummary, of11, shareText, type Group, type HistoryDoc, type LiveDoc } from './lineupRecord';

const fields = ['fixture', 'kickoff', 'league', 'team', 'opponent', 'home', 'correct', 'roles_right', 'roles_known', 'lines', 'hours_before', 'version', 'missed', 'wrong'];
const doc: LiveDoc = { fields, versions: [{ name: 'a' }, { name: 'b' }], excluded_no_official_xi: 2, rows: [
	[1, '2026-10-03T14:00:00+00:00', 39, 42, 50, 1, 11, 10, 11, [1, 1, 4, 4, 3, 3, 3, 3], 0.5, 0, [], []],
	[1, '2026-10-03T14:00:00+00:00', 39, 50, 42, 0, 9, 8, 9, [1, 1, 4, 3, 3, 3, 3, 2], 0.5, 0, [7, 8], [70, 80]],
	[2, '2026-10-05T19:00:00+00:00', 40, 63, 64, 1, 8, 6, 8, [1, 1, 4, 3, 3, 2, 3, 2], 30, 1, [7, 9, 10], [70, 90, 91]],
	[3, '2026-10-06T23:30:00+00:00', 39, 50, 33, 1, 10, 9, 10, [1, 1, 4, 4, 3, 3, 3, 2], 3, 1, [7], [70]]
] };
const rows = liveRows(doc);
const sum = (days: number | null = null, ids: number[] | null = null, shown = 50) => liveSummary(doc, rows, days, ids, 'Europe/London', shown, Date.parse('2026-10-08T00:00:00Z'));

describe('the live record', () => {
	const s = sum();
	it('totals the line-ups, the starters named and the perfect XIs', () => {
		expect(s).toMatchObject({ any: true, n: 4, correct: 38, perfect: 1, rolesRight: 33, rolesKnown: 38, matches: 3, excluded: 2 });
		expect(s.counts![11]).toBe(1);
		expect(s.counts![9]).toBe(1);
	});
	it('puts a late kick-off on the visitor\'s day, and counts by day while the record is short', () => {
		expect(s.first).toBe('2026-10-03');
		expect(s.last).toBe('2026-10-07'); // 23:30 UTC is past midnight in UK summer time
		expect(s.step).toBe('day');
		expect(s.trend).toEqual([['2026-10-07', 1, 10, 0], ['2026-10-05', 1, 8, 0], ['2026-10-03', 2, 20, 1]]);
	});
	it('adds up the four lines and how long before kick-off each was saved', () => {
		expect(s.lines).toEqual([4, 4, 16, 14, 12, 11, 12, 9]);
		expect(s.timing).toEqual([['Under 1 hour', 2, 20, 1], ['1–6 hours', 1, 10, 0], ['6–24 hours', 0, 0, 0], ['24 hours or more', 1, 8, 0]]);
	});
	it('groups by competition, club and model version', () => {
		expect(s.comps!.find((c) => c[0] === 39)).toEqual([39, 3, 30, 1, 27, 30]);
		expect(s.clubs!.find((c) => c[0] === 50)!.slice(0, 3)).toEqual([50, 2, 19]);
		expect(s.versions!.map((v) => [v[0], v[1]])).toEqual([[0, 2], [1, 2]]);
	});
	it('lists the players it got wrong twice or more, with the club they were at', () => {
		expect(s.missed).toEqual([[7, 50, 3]]);
		expect(s.wrong).toEqual([[70, 50, 3]]);
		expect(s.missedTotal).toBe(6);
	});
	it('lists the line-ups newest first, as many as asked for', () => {
		expect(sum(null, null, 2).rows!.map((r) => r.team)).toEqual([50, 63]);
	});
	it('narrows to a range and to competitions', () => {
		expect(sum(3).n).toBe(2);
		expect(sum(null, [40]).n).toBe(1);
		expect(sum(null, [999])).toMatchObject({ any: true, n: 0 });
	});
	it('counts by week once the record is longer than four weeks', () => {
		const long: LiveDoc = { ...doc, rows: [[9, '2026-08-01T14:00:00+00:00', 39, 42, 50, 1, 7, 5, 7, [1, 1, 4, 2, 3, 2, 3, 2], 2, 0, [], []], ...doc.rows] };
		const l = liveSummary(long, liveRows(long), null, null, 'Europe/London', 50);
		expect(l.step).toBe('week');
		expect(l.trend![0][0]).toBe('2026-10-05'); // the Monday of the latest week
	});
});

describe('the reconstructed history', () => {
	it('is the database\'s answer in the same shape', () => {
		const h = { any: true, total: 818, correct: 6285, perfect: 40, roles_right: 4821, roles_known: 6073, matches: 435, first: '2026-09-08', last: '2026-10-07',
			counts: { 9: 184, 11: 40 }, step: 'week', trend: [['2026-10-05', 21, 60, 0]], lines: [1, 1, 1, 1, 1, 1, 1, 1], comps: [], clubs: [], missed: [], wrong: [], missed_total: 2713,
			rows: [['2026-10-07', 1607, 1603, 1, 253, 8, [22235]]] } as unknown as HistoryDoc;
		const s = historySummary(h);
		expect(s).toMatchObject({ n: 818, correct: 6285, rolesKnown: 6073, first: '2026-09-08', missedTotal: 2713 });
		expect(s.counts).toHaveLength(12);
		expect(s.counts![9]).toBe(184);
		expect(s.rows![0]).toEqual({ day: '2026-10-07', team: 1607, opponent: 1603, home: true, league: 253, correct: 8, missed: [22235] });
	});
});

describe('clubs easiest and hardest to predict', () => {
	const club = (id: number, n: number, correct: number): Group => [id, n, correct, 0];
	it('needs enough clubs with enough line-ups', () => {
		expect(clubExtremes([club(1, 3, 30), club(2, 3, 20), club(3, 2, 22)])).toBeNull();
	});
	it('ranks by starters named per line-up, leaving out clubs with too few', () => {
		const x = clubExtremes([club(1, 3, 33), club(2, 3, 30), club(3, 4, 36), club(4, 3, 21), club(5, 5, 30), club(6, 3, 15), club(7, 1, 11)])!;
		expect(x.easiest.map((c) => c[0])).toEqual([1, 2, 3]);
		expect(x.hardest.map((c) => c[0])).toEqual([6, 5, 4]);
	});
	it('writes the figures', () => {
		expect(of11(9.512)).toBe('9.5 of 11');
		expect(shareText(40, 818)).toBe('4.9%');
		expect(shareText(1, 0)).toBe('–');
	});
});
