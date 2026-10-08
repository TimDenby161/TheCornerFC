import { describe, expect, test } from 'vitest';
import { eflBestTeam, eflClubRows, eflList, eflNext, eflSpan, fplList, fplSpan, partLines, predRows, priceLabel, priceStops, statusTag, versus, FPL_PARTS,
	type EflView, type FplView, type PredDoc } from './fantasy';

// Three players over two gameweeks: [player, name, team, position, fpl_position, price, fpl_status, fpl_chance, availability]
const FPL: PredDoc = {
	source: 'fpl', model: 'v1.6', gameweeks: [{ id: 8, first_kickoff: '2026-10-17T11:30:00Z' }, { id: 9, first_kickoff: '2026-10-24T11:30:00Z' }],
	teams: { 1: ['Arsenal', 'ARS'], 2: ['Brentford', 'BRE'] },
	fields: ['player', 'name', 'team', 'position', 'fpl_position', 'price', 'fpl_status', 'fpl_chance', 'availability'],
	cell_fields: ['gw', 'opponent', 'home', 'xp', 'minutes', 'goals', 'assists', 'p_clean_sheet', 'parts'],
	part_fields: ['appearance', 'goal', 'clean_sheet', 'card'],
	players: [[10, 'B. O&apos;Hara', 1, 'F', 'M', 95, 'a', null, null], [11, 'K. Stone', 1, 'D', 'D', 45, 'd', 75, null], [12, 'New Boy', 2, 'F', null, null, null, null, 'Missing Fixture']],
	cells: [
		[[0, 2, true, 6, 85, 0.5, 0.3, 0.4, [2, 2.5, 0.4, -0.1]], [1, 2, false, 5, 80, 0.4, 0.2, 0.3, [2, 2, 0.3, -0.1]]],
		[[0, 2, true, 4, 90, 0.05, 0.05, 0.4, [2, 0.3, 1.6, -0.2]]],
		[[0, 1, false, 3, 70, 0.3, 0.1, 0.2, [2, 1.2, 0, -0.001]]]
	]
};
const view = (over: Partial<FplView> = {}): FplView => ({ pos: 'all', q: '', sort: 'xp', mode: 'gw', gw: 0, price: [null, null], mine: false, target: false, ...over });
const none = new Map<number, [boolean, boolean]>();

describe('FPL predictions', () => {
	const rows = predRows(FPL);
	test('rows: names decoded, FPL position ahead of our own, matches named', () => {
		expect(rows[0].name).toBe("B. O'Hara");
		expect(rows[0].pos).toBe('M');
		expect(rows[2].pos).toBe('F');
		expect(rows[0].cells[1]).toMatchObject({ gw: 1, opponent: 2, home: false, xp: 5 });
		expect(versus(FPL, rows[0].cells.slice(0, 1))).toBe('v Brentford H');
		expect(versus(FPL, [])).toBe('No match (blank)');
	});
	test('one gameweek, or the next few summed', () => {
		expect(fplList(FPL, rows, view(), none).map((r) => [r.p.player, r.xp])).toEqual([[10, 6], [11, 4], [12, 3]]);
		expect(fplSpan(FPL, view({ mode: '5' }))).toEqual([0, 1]);
		const multi = fplList(FPL, rows, view({ mode: '5' }), none);
		expect(multi[0]).toMatchObject({ xp: 11, minutes: 165, price: 9.5 });
		expect(multi[0].value).toBeCloseTo(11 / 9.5);
		expect(fplList(FPL, rows, view({ gw: 1 }), none).map((r) => r.xp)).toEqual([5, 0, 0]);
	});
	test('filters: position, search by player or club, price (a player with no price is left out), marks', () => {
		expect(fplList(FPL, rows, view({ pos: 'M' }), none).map((r) => r.p.player)).toEqual([10]);
		expect(fplList(FPL, rows, view({ q: 'brent' }), none).map((r) => r.p.player)).toEqual([12]);
		expect(fplList(FPL, rows, view({ price: [null, 5] }), none).map((r) => r.p.player)).toEqual([11]);
		expect(fplList(FPL, rows, view({ price: [5, null] }), none).map((r) => r.p.player)).toEqual([10]);
		const marks = new Map<number, [boolean, boolean]>([[11, [true, false]], [12, [false, true]]]);
		expect(fplList(FPL, rows, view({ mine: true }), marks).map((r) => r.p.player)).toEqual([11]);
		expect(fplList(FPL, rows, view({ mine: true, target: true }), marks).map((r) => r.p.player)).toEqual([11, 12]);
		expect(fplList(FPL, rows, view({ sort: 'minutes' }), none).map((r) => r.p.player)).toEqual([11, 10, 12]);
	});
	test('price stops every £0.5m, and what the slider says', () => {
		const stops = priceStops(rows);
		expect(stops[0]).toBe(4.5);
		expect(stops[stops.length - 1]).toBe(9.5);
		expect(stops.length).toBe(11);
		expect(priceLabel(stops, 0, 10)).toBe('Any price');
		expect(priceLabel(stops, 0, 3)).toBe('Up to £6.0m');
		expect(priceLabel(stops, 2, 10)).toBe('£5.5m and over');
		expect(priceLabel(stops, 1, 2)).toBe('£5.0m to £5.5m');
	});
	test("a doubt: FPL's status first, then the injury list", () => {
		expect(statusTag(rows[0])).toBeNull();
		expect(statusTag(rows[1])).toEqual({ text: '75%', title: 'FPL status' });
		expect(statusTag({ fpl_status: 'i' })?.text).toBe('Injured');
		expect(statusTag(rows[2])).toEqual({ text: 'Out', title: 'On the injury list' });
	});
	test('where the points come from: parts summed, tiny ones dropped', () => {
		const [r] = fplList(FPL, rows, view({ mode: '5' }), none);
		expect(partLines(FPL, r, FPL_PARTS).map((x) => [x.label, x.figure, +x.value.toFixed(2)])).toEqual([
			['Minutes', '165', 4], ['Goals', '0.90', 4.5], ['Clean sheet', '', 0.7], ['Cards', '', -0.2]]);
		const [, , last] = fplList(FPL, rows, view(), none);
		expect(partLines(FPL, last, FPL_PARTS).map((x) => x.label)).toEqual(['Minutes', 'Goals']);
		expect(partLines(FPL, fplList(FPL, rows, view(), none)[1], FPL_PARTS)[2].figure).toBe('40%');
	});
});

describe('EFL Fantasy', () => {
	// ten players of one division over two gameweeks (a match names its gameweek by number)
	const pos = ['G', 'D', 'D', 'D', 'M', 'M', 'M', 'F', 'F', 'F'];
	const EFL: PredDoc = {
		model: 'efl v1', gameweeks: [{ id: 11, first_kickoff: '2026-10-08T18:45:00Z', start: '2026-10-08', end: '2026-10-14', started: true }, { id: 12, first_kickoff: '2026-10-17T14:00:00Z', start: '2026-10-15', end: '2026-10-21' }],
		teams: { 1: ['Leeds', 'LEE', 40], 2: ['Hull', 'HUL', 40], 3: ['Derby', 'DER', 40], 4: ['Luton', 'LUT', 41], 5: ['Stoke', 'STK', 40], 6: ['Burnley', 'BUR', 40] },
		leagues: { 40: 'Championship', 41: 'League One' },
		fields: ['player', 'name', 'team', 'position', 'corrected', 'availability'], cell_fields: ['gw', 'opponent', 'home', 'xp', 'minutes', 'goals', 'assists', 'parts'], part_fields: ['appearance'],
		// three from club 1 lead: only two may be picked
		players: pos.map((p, i) => [100 + i, `P${i}`, i === 0 ? 2 : i === 1 || i === 4 || i === 7 ? 1 : 2 + (i % 5), p, false, null]),
		cells: pos.map((_, i) => [[12, 2, true, 10 - i * 0.5, 90, 0.2, 0.1, [2]], [11, 3, false, 1, 90, 0.1, 0.1, [2]]]),
		clubs: { 1: [[12, 2, true, 4, 0.5, 0.3, [2.5, 0.8]]], 2: [[12, 1, false, 2, 0.2, 0.2, [1, 0.5]]], 4: [[12, 3, true, 5, 0.6, 0.4, [3, 1]]] },
		club_fields: ['gw', 'opponent', 'home', 'xp', 'p_win', 'p_clean_sheet', 'parts'], club_part_fields: ['win', 'clean_sheet']
	};
	const rows = predRows(EFL), clubs = eflClubRows(EFL);
	const v: EflView = { pos: 'all', league: 'all', q: '', sort: 'xp', mode: 'gw', gw: 1 };
	test('opens on the next gameweek to start', () => {
		expect(eflNext(EFL.gameweeks, Date.parse('2026-10-09T00:00:00Z'))).toBe(1);
		expect(eflNext(EFL.gameweeks, Date.parse('2026-12-01T00:00:00Z'))).toBe(0);
		expect(eflSpan(EFL, v, 1)).toEqual([12]);
		expect(eflSpan(EFL, { ...v, mode: '3' }, 1)).toEqual([12]);
	});
	test('suggested team: seven in a legal shape, two a club at most, captain counted twice, two clubs', () => {
		const best = eflBestTeam(rows, clubs, 12)!;
		expect(best.xi.length).toBe(7);
		expect(best.xi.filter((r) => r.p.position === 'G').length).toBe(1);
		const per = new Map<number, number>();
		for (const r of best.xi) per.set(r.p.team, (per.get(r.p.team) || 0) + 1);
		expect(Math.max(...per.values())).toBeLessThanOrEqual(2);
		expect(best.total).toBeCloseTo(best.xi.reduce((a, r) => a + r.xp, 0) + best.xi[0].xp);
		expect(best.clubs.map((r) => r.c.team)).toEqual([4, 1]);
		expect(eflBestTeam(rows, clubs, 99)).toBeNull();
	});
	test('lists: a division, a position, and each player with his division', () => {
		expect(rows[0].league).toBe(40);
		expect(eflList(EFL, rows, { ...v, pos: 'G' }, [12]).map((r) => r.p.player)).toEqual([100]);
		expect(eflList(EFL, rows, { ...v, league: '41' }, [12]).every((r) => r.p.league === 41)).toBe(true);
		expect(eflList(EFL, rows, v, [11, 12])[0].xp).toBe(11);
	});
});
