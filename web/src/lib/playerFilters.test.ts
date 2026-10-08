import { describe, expect, it } from 'vitest';
import { handlesRange, parseRange, posRank, rangeLabel, rangeParam, rangeStops, rangeText, selectedGroups, stopIndex, whoMatches, whoOptions, type PlayerFacets } from './playerFilters';
import type { Site } from './site';

const facets: PlayerFacets = {
	players: 5, age: [16, 42], ability: [42, 97], minutes: 1838, positions: { ST: 3 },
	clubs: [[42, 39], [33, 39], [157, 78], [900, 40], [901, 141]], nats: ['Spain', 'England', 'Côte d\'Ivoire']
};

describe('ranges in the address', () => {
	it('reads both ends, either end open, and ignores anything else', () => {
		expect(parseRange('20-25')).toEqual([20, 25]);
		expect(parseRange('-25')).toEqual([null, 25]);
		expect(parseRange('20-')).toEqual([20, null]);
		expect(parseRange(null)).toEqual([null, null]);
		expect(parseRange('abc')).toEqual([null, null]);
		expect(parseRange('1;drop')).toEqual([null, null]);
	});
	it('writes them back the same way', () => {
		expect(rangeText([20, null])).toBe('20-');
		expect(rangeText([null, null])).toBeNull();
	});
	it('sends whole numbers to the database', () => {
		expect(rangeParam([19.2, 25.8])).toEqual([20, 25]);
		expect(rangeParam([null, 30])).toEqual([null, 30]);
	});
});

describe('rangeStops', () => {
	it('has every age and every whole Ability', () => {
		expect(rangeStops('age', facets, 0)).toHaveLength(27);
		expect(rangeStops('ab', facets, 0)[0]).toBe(42);
		expect(rangeStops('ab', facets, 0).at(-1)).toBe(97);
	});
	it('steps minutes a match at a time, past the most anyone has', () => {
		const s = rangeStops('mins', facets, 0);
		expect(s.slice(0, 3)).toEqual([0, 90, 180]);
		expect(s.at(-1)).toBe(1890);
	});
	it('makes club ranks finer at the top and ends on the number of ranked clubs', () => {
		expect(rangeStops('crank', facets, 2346)).toEqual([1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000, 2346]);
		expect(rangeStops('crank', facets, 60)).toEqual([1, 5, 10, 20, 30, 50, 60]);
	});
});

describe('handles', () => {
	const stops = [1, 5, 10, 20, 50];
	it('stand on the nearest stop inside a range from a link', () => {
		expect(stopIndex(stops, null, 0)).toBe(0);
		expect(stopIndex(stops, null, 1)).toBe(4);
		expect(stopIndex(stops, 7, 0)).toBe(2);
		expect(stopIndex(stops, 7, 1)).toBe(1);
		expect(stopIndex(stops, 99, 0)).toBe(4);
	});
	it('at either end leave that end open', () => {
		expect(handlesRange(stops, 0, 4)).toEqual([null, null]);
		expect(handlesRange(stops, 1, 3)).toEqual([5, 20]);
		expect(handlesRange(stops, 0, 2)).toEqual([null, 10]);
	});
	it('are described in words', () => {
		expect(rangeLabel('crank', stops, 0, 4)).toBe('All');
		expect(rangeLabel('crank', stops, 0, 2)).toBe('Top 10');
		expect(rangeLabel('crank', stops, 2, 4)).toBe('10 down');
		expect(rangeLabel('ab', stops, 0, 2)).toBe('Up to 10');
		expect(rangeLabel('ab', stops, 2, 4)).toBe('10+');
		expect(rangeLabel('mins', stops, 1, 3)).toBe('5–20');
		expect(rangeLabel('age', stops, 0, 4)).toBe('All ages');
		expect(rangeLabel('age', stops, 2, 2)).toBe('10');
	});
});

describe('positions', () => {
	it('turns picked positions into the groups they are rated in, each once', () => {
		expect(selectedGroups(['LB', 'RB', 'ST'])).toEqual(['FB', 'ST']);
		expect(selectedGroups([])).toEqual([]);
	});
	it('ranks a player as his best of the picked groups, or not at all', () => {
		expect(posRank({ W: 95.5, AM: 87.5 }, ['AM', 'W'])).toBe(95.5);
		expect(posRank({ W: 95.5 }, ['CB'])).toBeNull();
		expect(posRank(null, ['CB'])).toBeNull();
	});
});

describe('club and nationality options', () => {
	const site = {
		competitions: { 39: { name: 'Premier League', country: 'England', type: 'League' }, 40: { name: 'Championship', country: 'England', type: 'League' }, 78: { name: 'Bundesliga', country: 'Germany', type: 'League' }, 141: { name: 'Segunda División', country: 'Spain', type: 'League' } },
		teams: { 42: 'Arsenal', 33: 'Manchester United', 157: 'Bayern München', 900: 'Racing', 901: 'Racing' }
	} as unknown as Site;
	const countries = [{ name: 'England', leagues: [39, 40], region: null }, { name: 'Germany', leagues: [78], region: null }];
	const who = whoOptions(site, facets, countries);
	it('adds the league to a name two clubs share', () => {
		expect(who.clubs.map((c) => c.name)).toEqual(['Arsenal', 'Bayern München', 'Manchester United', 'Racing (Championship)', 'Racing (Segunda División)']);
	});
	it('lists leagues in the competition menu\'s order, others after', () => {
		expect(who.leagues.map((l) => l.id)).toEqual([39, 40, 78, 141]);
		expect(who.leagues[0].clubs).toEqual([42, 33]);
	});
	it('sorts nationalities and matches without accents, starts of names first', () => {
		expect(who.nats.map((n) => n.name)).toEqual(["Côte d'Ivoire", 'England', 'Spain']);
		expect(whoMatches(who.nats, 'cote').map((n) => n.name)).toEqual(["Côte d'Ivoire"]);
		expect(whoMatches(who.clubs, 'munchen').map((c) => c.id)).toEqual([157]);
		expect(whoMatches(who.clubs, 'r').map((c) => c.name).slice(0, 2)).toEqual(['Racing (Championship)', 'Racing (Segunda División)']);
	});
});
