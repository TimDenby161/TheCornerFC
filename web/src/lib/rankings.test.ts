import { describe, expect, it } from 'vitest';
import { clubPlaces, clubRows, clubs, tiers, type RankingsDoc } from './rankings';

const doc: RankingsDoc = {
	generated_at: '2026-10-07T14:16:17+00:00',
	fields: ['team', 'league', 'current', 'st', 'lt', 'played', 'form', 'in_league', 'attack', 'defence', 'home', 'away'],
	rankings: [
		[157, 78, 1118.4, 1117.5, 1118.2, 287, 33.1, 1, 1189.4, 1047.4, 1124, 1112.7],
		[42, 39, 1093.9, 1094.1, 1095.7, 333, 15.1, 1, 1071.9, 1115.9, 1089.8, 1097.9],
		[50, 39, 1109.6, 1107.7, 1091.8, 368, null, 1, 1128.3, 1090.9, 1105.1, 1114.1],
		[900, 39, 900.4, 900, 1095.7, 10, -4, 0, 900, 900, 900, 900]
	]
};
const all = clubs(doc);

describe('clubs', () => {
	it('names each figure by its field', () => {
		expect(all[0]).toMatchObject({ team: 157, league: 78, lt: 1118.2, in_league: 1 });
	});
	it('works the gap out from the rounded figures, as the table shows them', () => {
		expect(all[2].trend).toBe(1110 - 1092);
	});
});

describe('clubPlaces', () => {
	const places = clubPlaces(all);
	it('ranks every club in the world, equal ratings sharing a place', () => {
		expect(places.get(157)!.world).toBe(1);
		expect(places.get(42)!.world).toBe(2);
		expect(places.get(900)!.world).toBe(2);
		expect(places.get(50)!.world).toBe(4);
	});
	it('ranks a club in its league among this season\'s clubs only', () => {
		expect(places.get(42)).toMatchObject({ dom: 1, domOf: 2 });
		expect(places.get(50)).toMatchObject({ dom: 2, domOf: 2 });
		expect(places.get(900)).toMatchObject({ dom: null, domOf: null });
	});
});

describe('tiers', () => {
	it('colours by place among every ranked club', () => {
		const tier = tiers(all, 'lt');
		expect(tier(1118.2)).toBe(2);       // 1st of 4 is the top 25%: past the top 20%, inside the top half
		expect(tier(1091.8)).toBe(1);
	});
});

describe('clubRows', () => {
	it('leaves out clubs with no tracked league this season', () => {
		expect(clubRows(all, 'lt', null).map((c) => c.team)).toEqual([157, 42, 50]);
	});
	it('keeps one league when asked, and puts a club with no figure last', () => {
		expect(clubRows(all, 'form', 39).map((c) => c.team)).toEqual([42, 50]);
	});
});
