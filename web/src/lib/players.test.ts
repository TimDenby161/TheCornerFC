import { describe, expect, it } from 'vitest';
import { tableCountries, type Cups } from './clubTable';
import { NO_FILTERS, countParams, decodeEntities, listParams, playerCounts, playerRows, searchParams, sortKey, type Facets, type PlayerChoices } from './players';
import { clubs } from './rankings';
import type { Site } from './site';

const site: Site = {
	generated_at: '',
	competitions: {
		2: { name: 'UEFA Champions League', country: 'World', type: 'Cup' },
		39: { name: 'Premier League', country: 'England', type: 'League' },
		78: { name: 'Bundesliga', country: 'Germany', type: 'League' },
		307: { name: 'Pro League', country: 'Saudi-Arabia', type: 'League' }
	},
	teams: { 33: 'Manchester United', 42: 'Arsenal', 157: 'Bayern München', 2932: 'Al-Hilal' },
	match_fields: [],
	player_fields: ['id', 'name', 'position', 'rank', 'team', 'league', 'seasons', 'season', 'ord'],
	player_season_fields: ['minutes', 'goals', 'assists'],
	player_seasons: [2026, 2025, 2024],
	player_future_seasons: [2027, 2028]
};
const fields = ['team', 'league', 'current', 'st', 'lt', 'played', 'form', 'in_league', 'attack', 'defence', 'home', 'away'];
const all = clubs({ generated_at: '', fields, rankings: [[157, 78, 1100, 1, 1100, 1, 1, 1, 1, 1, 1, 1], [42, 39, 1090, 1, 1090, 1, 1, 1, 1, 1, 1, 1], [33, 39, 1040, 1, 1040, 1, 1, 1, 1, 1, 1, 1], [2932, 307, 950, 1, 950, 1, 1, 1, 1, 1, 1, 1]] });
const countries = tableCountries(site, all);
const cups: Cups = new Map([[2, new Set([157, 42])]]);
const facets: Facets = { players: 4, age: [16, 40], ability: [40, 97], minutes: 1800, positions: {}, nats: [], clubs: [[157, 78], [42, 39], [33, 39], [2932, 307]] };
const choose = (o: Partial<PlayerChoices> = {}): PlayerChoices => ({ filter: 'all', excluded: new Set(), search: '', sort: 's2026', ...NO_FILTERS, ...o });
const ask = (o: Partial<PlayerChoices> = {}) => listParams(site, all, countries, cups, facets, choose(o));

describe('playerRows', () => {
	it('names the fields, decodes a name and marks a player whose ranks were blanked', () => {
		const [a, b] = playerRows(site, [[1, 'N. O&apos;Reilly', 'CM', 80.2, 42, 39, [80.2, 79, null], [900, 3, 1], 0], [2, 'M. de Roon', 'CM', null, 33, 39, null, [38, 0, 0], 1]]);
		expect(a).toMatchObject({ name: "N. O'Reilly", locked: false, season: { minutes: 900, goals: 3, assists: 1 } });
		expect(b).toMatchObject({ locked: true, rank: null });
	});
	it('leaves an ordinary name alone', () => {
		expect(decodeEntities('Lamine Yamal')).toBe('Lamine Yamal');
	});
});

describe('sortKey', () => {
	const key = (asked: string | null, open = true) => sortKey(asked, site.player_seasons, site.player_future_seasons, open);
	it('is the current season unless something else is asked for', () => {
		expect(key(null)).toBe('s2026');
		expect(key('nonsense')).toBe('s2026');
		expect(key('s1999')).toBe('s2026');
	});
	it('takes age, goals and assists, a past season or a projected one', () => {
		expect(key('age')).toBe('age');
		expect(key('ga')).toBe('ga');
		expect(key('s2024')).toBe('s2024');
		expect(key('f2028')).toBe('f2028');
	});
	it('puts the position rank in Ability\'s place while positions are picked', () => {
		const withPos = (asked: string | null, open = true) => sortKey(asked, site.player_seasons, site.player_future_seasons, open, ['ST']);
		expect(withPos(null)).toBe('pos');
		expect(withPos('s2026')).toBe('pos');
		expect(withPos('s2024')).toBe('s2024');
		expect(withPos('age', false)).toBe('age');
		expect(key('pos')).toBe('s2026');
	});
	it('can\'t sort on a season column that is closed', () => {
		expect(key('s2024', false)).toBe('s2026');
		expect(key('age', false)).toBe('age');
	});
});

describe('listParams', () => {
	it('asks for everyone by default, sorted on the current season', () => {
		expect(ask()).toEqual({ p_sort: 's0' });
	});
	it('sends a league, a country or a cup\'s clubs', () => {
		expect(ask({ filter: '39' })).toMatchObject({ p_leagues: [39] });
		expect(ask({ filter: 'c:Germany' })).toMatchObject({ p_leagues: [78] });
		expect(ask({ filter: 'e:2' })).toMatchObject({ p_teams: [157, 42] });
	});
	it('sends the excluded leagues', () => {
		expect(ask({ excluded: new Set(['England']) })).toMatchObject({ p_not_leagues: [39] });
		expect(ask({ excluded: new Set(['r:Asia']) })).toMatchObject({ p_not_leagues: [307] });
	});
	it('names seasons by their place, newest first', () => {
		expect(ask({ sort: 's2024' }).p_sort).toBe('s2');
		expect(ask({ sort: 'f2028' }).p_sort).toBe('f1');
		expect(ask({ sort: 'age' }).p_sort).toBe('age');
	});
	it('sends the side filters: ranges, positions, clubs and nationalities', () => {
		expect(ask({ ranges: { ...NO_FILTERS.ranges, age: [null, 21], crank: [null, 50] } })).toMatchObject({ p_age: [null, 21], p_crank: [null, 50] });
		expect(ask({ positions: ['LB', 'RB'], nats: ['Spain'] })).toMatchObject({ p_positions: ['LB', 'RB'], p_nats: ['Spain'] });
	});
	it('shows a picked club\'s players whatever league is selected', () => {
		const p = ask({ clubs: [42], filter: '78', excluded: new Set(['England']) });
		expect(p.p_teams).toEqual([42]);
		expect(p.p_leagues).toBeUndefined();
		expect(p.p_not_leagues).toBeUndefined();
	});
	it('sorts by his rank in the picked positions\' groups', () => {
		expect(ask({ positions: ['LB', 'ST'], sort: 'pos' })).toMatchObject({ p_sort: 'pos', p_groups: ['FB', 'ST'] });
	});
	it('searches every player, whatever the menu and the exclusions say', () => {
		const p = ask({ search: ' Man Utd ', filter: '78', excluded: new Set(['England']) });
		expect(p.p_leagues).toBeUndefined();
		expect(p.p_not_leagues).toBeUndefined();
		expect(p.p_q).toBe('man utd');
		expect(p.p_words).toEqual(['man|0|33', 'utd|0|33']);
	});
});

describe('searchParams', () => {
	it('finds the clubs a word fits by short form, league and country', () => {
		expect(searchParams(site, all, facets, 'epl').p_words).toEqual(['epl|0|42,33']);
		expect(searchParams(site, all, facets, 'munich').p_words).toEqual(['munich|0|157']);
		expect(searchParams(site, all, facets, 'yamal').p_words).toEqual(['yamal|0|']);
	});
});

describe('counts', () => {
	it('asks for counts with the exclusions applied', () => {
		expect(countParams(site, choose())).toEqual({ p_count: true });
		expect(countParams(site, choose({ excluded: new Set(['Germany']) }))).toEqual({ p_not_leagues: [78], p_count: true });
		expect(countParams(site, choose({ positions: ['ST'], nats: ['Spain'] }))).toEqual({ p_positions: ['ST'], p_nats: ['Spain'], p_count: true });
	});
	it('adds them up for a league, a country, a cup and all', () => {
		const countOf = playerCounts([[39, 42, 25], [39, 33, 24], [78, 157, 26], [307, 2932, 20]], countries, cups);
		expect(countOf('all')).toBe(95);
		expect(countOf('39')).toBe(49);
		expect(countOf('c:Germany')).toBe(26);
		expect(countOf('r:Asia')).toBe(20);
		expect(countOf('e:2')).toBe(51);
	});
});
