import { describe, expect, it } from 'vitest';
import { clubSearchText, filterMenu, isExcluded, knownFilter, tableCountries, tableRows, type Cups } from './clubTable';
import { clubs } from './rankings';
import type { Site } from './site';

const site: Site = {
	generated_at: '',
	competitions: {
		2: { name: 'UEFA Champions League', country: 'World', type: 'Cup' },
		39: { name: 'Premier League', country: 'England', type: 'League' },
		40: { name: 'Championship', country: 'England', type: 'League' },
		78: { name: 'Bundesliga', country: 'Germany', type: 'League' },
		113: { name: 'Allsvenskan', country: 'Sweden', type: 'League' },
		307: { name: 'Pro League', country: 'Saudi-Arabia', type: 'League' }
	},
	teams: { 33: 'Manchester United', 42: 'Arsenal', 63: 'Leeds', 157: 'Bayern München', 364: 'Djurgården', 2932: 'Al-Hilal', 900: 'Old Club' },
	match_fields: []
};
const fields = ['team', 'league', 'current', 'st', 'lt', 'played', 'form', 'in_league', 'attack', 'defence', 'home', 'away'];
const row = (team: number, league: number, lt: number, in_league = 1) => [team, league, lt + 5, lt, lt, 100, 1, in_league, lt, lt, lt, lt];
const all = clubs({ generated_at: '', fields, rankings: [row(157, 78, 1118), row(42, 39, 1096), row(33, 39, 1049), row(63, 40, 1017), row(364, 113, 900), row(2932, 307, 950), row(900, 39, 990, 0)] });
const countries = tableCountries(site, all);
const cups: Cups = new Map([[2, new Set([157, 42, 900])]]);
const pick = (o: Partial<Parameters<typeof tableRows>[4]> = {}) =>
	tableRows(site, all, countries, cups, { filter: 'all', excluded: new Set(), search: '', sort: 'lt', ...o });
const teams = (o?: Parameters<typeof pick>[0]) => pick(o).rows.map((r) => r.team);

describe('tableCountries', () => {
	it('puts the big five first, then the rest by name, each under its region', () => {
		expect(countries.map((c) => [c.name, c.region])).toEqual([['England', null], ['Germany', null], ['Saudi Arabia', 'Asia'], ['Sweden', 'Scandinavia']]);
		expect(countries[0].leagues).toEqual([39, 40]);
	});
});

describe('knownFilter', () => {
	it('takes a league, country, region or cup this site has, and nothing else', () => {
		for (const f of ['all', '39', 'c:England', 'r:Scandinavia', 'e:all', 'e:2', 'k:45']) expect(knownFilter(f, site, countries)).toBe(true);
		for (const f of [null, '', '2', '9999', 'c:Narnia', 'r:Atlantis', 'e:45', 'x:1', "39'"]) expect(knownFilter(f, site, countries)).toBe(false);
	});
});

describe('tableRows', () => {
	it('lists the clubs in a tracked league this season, highest first', () => {
		expect(teams()).toEqual([157, 42, 33, 63, 2932, 364]);
		expect(pick().wide).toBe(true);
	});
	it('keeps one league, a country or a region', () => {
		expect(teams({ filter: '39' })).toEqual([42, 33]);
		expect(pick({ filter: '39' }).wide).toBe(false);
		expect(teams({ filter: 'c:England' })).toEqual([42, 33, 63]);
		expect(teams({ filter: 'r:Scandinavia' })).toEqual([364]);
	});
	it('shows a cup\'s clubs whether or not they are in a tracked league', () => {
		expect(teams({ filter: 'e:2' })).toEqual([157, 42, 900]);
	});
	it('hides excluded countries and continents', () => {
		expect(teams({ excluded: new Set(['England']) })).toEqual([157, 2932, 364]);
		expect(teams({ excluded: new Set(['r:Europe']) })).toEqual([2932]);
		expect(teams({ filter: 'e:2', excluded: new Set(['England']) })).toEqual([157]);
	});
	it('searches every ranked club, whatever the menu and the exclusions say', () => {
		expect(teams({ search: 'man utd', filter: '78', excluded: new Set(['England']) })).toEqual([33]);
		expect(teams({ search: 'old' })).toEqual([900]);
		expect(teams({ search: 'bayern munich' })).toEqual([157]);
		expect(teams({ search: 'epl' })).toEqual([42, 33]);
	});
});

describe('clubSearchText', () => {
	it('folds accents and adds short forms', () => {
		expect(clubSearchText(site, all[0])).toContain(' bayern munchen ');
		expect(clubSearchText(site, all[2])).toContain(' utd ');
	});
});

describe('isExcluded', () => {
	it('never hides an international competition', () => {
		expect(isExcluded(site, new Set(['r:Europe']), 2)).toBe(false);
	});
});

describe('filterMenu', () => {
	const menu = filterMenu(site, all, countries, cups, '40', new Set());
	const chips = menu.nodes.flatMap((n) => (n.sep ? [] : [n, ...(n.children || []).flatMap((c) => (c.sep ? [] : [c, ...(c.children || [])]))])).flatMap((n) => (n.sep ? [] : [n]));
	const find = (v: string) => chips.find((n) => n.chip.value === v)!;
	it('names the choice in full and counts it', () => {
		expect(menu.name).toBe('England · Championship');
		expect(menu.count).toBe(1);
	});
	it('opens the country the choice is in', () => {
		expect(find('c:England').open).toBe(true);
		expect(find('c:England').chip.hasActive).toBe(true);
		expect(find('40').chip.pressed).toBe(true);
	});
	it('gives a country with one league a plain chip for that league', () => {
		expect(find('78').chip.label).toBe('Germany');
		expect(find('78').children).toBeUndefined();
	});
	it('counts clubs, a cup\'s too', () => {
		expect(find('all').chip.count).toBe(6);
		expect(find('c:England').chip.count).toBe(3);
		expect(find('e:2').chip.count).toBe(3);
		expect(find('r:Scandinavia').chip.count).toBe(1);
	});
});
