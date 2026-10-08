import { describe, expect, it } from 'vitest';
import { avgRating, chanceText, fixtureRows, formPoints, headline, leagueAverages, leagueClubs, leagueRanked, leagueRounds, pickSort, projectable, projectGroup, roundLabel, seasonLabel, sortRows, tableRows, type Cols, type Fixture, type LeagueFile, type TableRow } from './league';
import { clubs } from './rankings';
import type { Site } from './site';

const lg: LeagueFile = {
	id: 39, season: 2026, start: '2026-08-21',
	table_fields: ['group', 'rank', 'team', 'played', 'win', 'draw', 'lose', 'gf', 'ga', 'gd', 'points', 'form', 'description'],
	table: [['PL', 1, 50, 5, 5, 0, 0, 13, 5, 8, 15, 'WWWWW', 'Champions League'], ['PL', 2, 42, 5, 4, 0, 1, 9, 5, 4, 12, 'LWWWW', 'Champions League'], ['PL', 3, 51, 5, 3, 1, 1, 14, 3, 11, 10, 'WWDLW', null]],
	fixture_fields: ['id', 'kickoff', 'round', 'home', 'away', 'status', 'hg', 'ag', 'pen_h', 'pen_a', 'home_xg', 'away_xg', 'p_home', 'p_draw', 'p_away'],
	fixtures: [
		[1, '2026-09-19T14:00:00+00:00', 'Regular Season - 5', 51, 42, 'FT', 3, 0, null, null, null, null, null, null, null],
		[2, '2026-10-10T11:30:00+00:00', 'Regular Season - 6', 42, 50, 'NS', null, null, null, null, 1.6, 1.4, 0.4, 0.26, 0.34],
		[3, '2026-10-17T14:00:00+00:00', 'Regular Season - 7', 50, 51, 'NS', null, null, null, null, 2.1, 0.9, 0.62, 0.21, 0.17],
		[4, '2026-10-24T14:00:00+00:00', 'Regular Season - 8', 51, 42, 'NS', null, null, null, null, null, null, 0.3, 0.3, 0.4]
	],
	recent_xg_fields: ['xg90', 'xga90', 'games'], recent_xg: { 50: [2.1, 0.8, 5] }, teams: { 50: 'Manchester City' },
	cut: true, projected_fields: ['group', 'place', 'team', 'left', 'points'], projected: [['PL', 1, 50, 33, 81]]
};
const table = tableRows(lg), fixtures = fixtureRows(lg);

describe('reading a league\'s file', () => {
	it('names the table\'s figures and adds each club\'s recent xG', () => {
		expect(table[0]).toMatchObject({ rank: 1, team: 50, points: 15, xg90: 2.1, xga90: 0.8, xg_games: 5 });
		expect(table[1]).toMatchObject({ team: 42, xg90: null, xg_games: 0 });
		expect(fixtures[1]).toMatchObject({ id: 2, home: 42, away: 50, p_home: 0.4 });
		expect(headline(lg)).toEqual([{ group: 'PL', place: 1, team: 50, left: 33, points: 81 }]);
	});
	it('labels a winter season by two years and a calendar season by one', () => {
		expect(seasonLabel(lg)).toBe('2026/27');
		expect(seasonLabel({ ...lg, start: '2026-02-20' })).toBe('2026');
		expect(roundLabel('Regular Season - 6')).toBe('Round 6');
		expect(roundLabel('Quarter-finals')).toBe('Quarter-finals');
	});
});

const fields = ['team', 'league', 'current', 'st', 'lt', 'played', 'form', 'in_league', 'attack', 'defence', 'home', 'away'];
const all = clubs({ generated_at: '', fields, rankings: [[50, 39, 1110, 1, 1092, 1, 1, 1, 1, 1, 1, 1], [42, 39, 1094, 1, 1096, 1, 1, 1, 1, 1, 1, 1], [51, 39, 1080, 1, 1047, 1, 1, 1, 1, 1, 1, 1], [900, 39, 990, 1, 990, 1, 1, 0, 1, 1, 1, 1], [157, 78, 1118, 1, 1118, 1, 1, 1, 1, 1, 1, 1]] });
describe('clubs and averages', () => {
	it('lists a league\'s clubs this season, strongest first, and averages them', () => {
		expect(leagueClubs(all, 39).map((c) => c.team)).toEqual([42, 50, 51]);
		expect(Math.round(avgRating(leagueClubs(all, 39))!)).toBe(1078);
		expect(avgRating([])).toBeNull();
	});
	it('adds anyone in the table, or in the fixtures of a cup with no table', () => {
		expect(leagueRanked(all, 39, table, fixtures).map((c) => c.team)).toEqual([42, 50, 51]);
		expect(leagueRanked(all, 45, [], [{ home: 157, away: 900 } as Fixture]).map((c) => c.team)).toEqual([157, 900]);
	});
	it('gives every league with rated clubs its averages', () => {
		const site = { competitions: { 39: { name: 'Premier League', country: 'England', type: 'League' }, 78: { name: 'Bundesliga', country: 'Germany', type: 'League' }, 45: { name: 'FA Cup', country: 'England', type: 'Cup' }, 61: { name: 'Ligue 1', country: 'France', type: 'League' } } } as unknown as Site;
		const avgs = leagueAverages(site, all);
		expect(avgs.map((a) => a.lid)).toEqual([39, 78]);
		expect(avgs[0]).toMatchObject({ clubs: 3, trend: Math.round(avgs[0].current) - Math.round(avgs[0].lt) });
	});
});

describe('sorting a table', () => {
	const cols: Cols<TableRow> = { rank: { dir: 1, val: (r) => r.rank }, gd: { dir: -1, val: (r) => r.gd }, xg90: { dir: -1, val: (r) => r.xg90 }, form: { dir: -1, val: (r) => formPoints(r.form) } };
	it('sorts a column best first, and the other way when asked again', () => {
		expect(sortRows(table, pickSort(cols, 'rank', 'gd', false), cols).map((r) => r.team)).toEqual([51, 50, 42]);
		expect(sortRows(table, pickSort(cols, 'rank', 'gd', true), cols).map((r) => r.team)).toEqual([42, 50, 51]);
	});
	it('puts blanks last and falls back to the table\'s order for a column it doesn\'t have', () => {
		expect(sortRows(table, pickSort(cols, 'rank', 'xg90', false), cols).map((r) => r.team)).toEqual([50, 42, 51]);
		expect(pickSort(cols, 'rank', 'nonsense', false)).toEqual({ key: 'rank', dir: 1 });
	});
	it('scores form by points', () => {
		expect(formPoints('WWDLW')).toBe(10);
		expect(formPoints(null)).toBeNull();
	});
});

describe('the projected table', () => {
	// a fixed source of chance, so the test gives the same answer every time
	const seeded = (seed: number) => () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
	const sims = projectable(fixtures);
	it('plays out only the fixtures the model has projected', () => {
		expect(sims.map((f) => f.id)).toEqual([2, 3]);
	});
	const proj = projectGroup(table, sims, 2000, seeded(7));
	it('counts each club\'s matches left and expected results on top of the table so far', () => {
		const city = proj.find((p) => p.team === 50)!;
		expect(city.left).toBe(2);
		expect(city.w).toBeCloseTo(5 + 0.34 + 0.62, 6);
		expect(city.d + city.w + city.l).toBeCloseTo(5 + 2, 6);
	});
	it('gives every club chances for every place that add up to one, the leaders likeliest to finish top', () => {
		for (const p of proj) expect(p.pos.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6);
		const top = (team: number) => proj.find((p) => p.team === team)!.pos[0];
		expect(top(50)).toBeGreaterThan(top(42));
		expect(top(42)).toBeGreaterThan(top(51));
		expect(proj[0].team).toBe(50);
		expect(proj[0].pts).toBeGreaterThan(15);
	});
	it('writes a chance in words at the extremes', () => {
		expect(chanceText(0)).toBe('–');
		expect(chanceText(0.004)).toBe('<1%');
		expect(chanceText(0.997)).toBe('>99%');
		expect(chanceText(1)).toBe('100%');
		expect(chanceText(0.426)).toBe('43%');
	});
});

describe('a league\'s rounds', () => {
	it('opens on the round with the next fixture, else the last', () => {
		expect(leagueRounds(fixtures)).toEqual({ rounds: ['Regular Season - 5', 'Regular Season - 6', 'Regular Season - 7', 'Regular Season - 8'], open: 'Regular Season - 6' });
		expect(leagueRounds(fixtures.slice(0, 1)).open).toBe('Regular Season - 5');
		expect(leagueRounds([]).open).toBeNull();
	});
});
