import { describe, expect, it } from 'vitest';
import { cupEntrants, cupTeamsLeft, type LeagueDoc } from './cups';

const fixture_fields = ['id', 'kickoff', 'round', 'home', 'away', 'status', 'hg', 'ag', 'pen_h', 'pen_a'];
const table_fields = ['group', 'rank', 'team'];
const cup = (fixtures: LeagueDoc['fixtures'], table: LeagueDoc['table'] = []): LeagueDoc => ({ fixture_fields, fixtures, table_fields, table });

describe('cupTeamsLeft', () => {
	it('puts out the loser of a finished tie and keeps a tie still to play', () => {
		const left = cupTeamsLeft(cup([
			[1, '2026-09-01T19:00', 'Round 1', 10, 11, 'FT', 2, 0, null, null],
			[2, '2026-09-01T19:00', 'Round 1', 12, 13, 'NS', null, null, null, null]
		]));
		expect([...left].sort()).toEqual([10, 12, 13]);
	});
	it('settles a two-legged tie on aggregate, then on penalties', () => {
		const left = cupTeamsLeft(cup([
			[1, '2026-09-01T19:00', 'Semi', 10, 11, 'FT', 1, 0, null, null],
			[2, '2026-09-08T19:00', 'Semi', 11, 10, 'FT', 3, 1, null, null],
			[3, '2026-09-01T19:00', 'Semi', 12, 13, 'PEN', 1, 1, 4, 5]
		]));
		expect([...left].sort()).toEqual([11, 13]);
	});
	it('on a level tie with no shoot-out recorded, keeps the club that plays on', () => {
		const left = cupTeamsLeft(cup([
			[1, '2026-09-01T19:00', 'Round 1', 10, 11, 'FT', 1, 1, null, null],
			[2, '2026-09-20T19:00', 'Round 2', 11, 14, 'NS', null, null, null, null]
		]));
		expect(left.has(10)).toBe(false);
		expect(left.has(11)).toBe(true);
	});
	it('ignores a match that was called off', () => {
		const left = cupTeamsLeft(cup([[1, '2026-09-01T19:00', 'Round 1', 10, 11, 'PST', null, null, null, null]]));
		expect(left.size).toBe(0);
	});
	it('puts out the group clubs that are not in the knockout ties that follow', () => {
		const left = cupTeamsLeft(cup([
			[1, '2026-09-01T19:00', 'Group A', 10, 11, 'FT', 2, 0, null, null],
			[2, '2026-10-01T19:00', 'Quarter-finals', 10, 12, 'NS', null, null, null, null]
		]));
		expect([...left].sort()).toEqual([10, 12]);
	});
});

describe('cupEntrants', () => {
	it('is the league phase once there is a table', () => {
		expect([...cupEntrants(cup([[1, '2026-07-07T16:00', 'Qualifying', 1, 2, 'FT', 2, 0, null, null]], [['UCL', 1, 85], ['UCL', 2, 50]]))]).toEqual([85, 50]);
	});
	it('is everyone drawn in it before that', () => {
		expect([...cupEntrants(cup([[1, '2026-07-07T16:00', 'Qualifying', 1, 2, 'FT', 2, 0, null, null]]))]).toEqual([1, 2]);
	});
});
