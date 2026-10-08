import { describe, expect, it } from 'vitest';
import { oldAddress, pageHref, tabFor } from './menu';

describe('old shared links', () => {
	it('go to the same page here, with their choices', () => {
		expect(oldAddress('#/clubs?c=39&sort=form')).toBe('/clubs?c=39&sort=form');
		expect(oldAddress('#/players?age=-21&pos=ST&club=42&nat=England')).toBe('/players?age=-21&pos=ST&club=42&nat=England');
		expect(oldAddress('#/club/42/matches')).toBe('/club/42/matches');
		expect(oldAddress('#/league/39/table')).toBe('/league/39/table');
		expect(oldAddress('#/nation/Korea%20Republic/players')).toBe('/nation/Korea%20Republic/players');
		expect(oldAddress('#/model-vs-market')).toBe('/model-vs-market');
		expect(oldAddress('#/matches?c=e:2&d=2026-10-13')).toBe('/matches?c=e:2&d=2026-10-13');
	});
	it('drop the first tab\'s name, which has no address of its own here', () => {
		expect(oldAddress('#/club/42/overview')).toBe('/club/42');
		expect(oldAddress('#/player/1100/overview')).toBe('/player/1100');
	});
	it('carry the owner\'s fantasy pages over too', () => {
		expect(oldAddress('#/fpl')).toBe('/fpl');
		expect(oldAddress('#/my-fpl-team')).toBe('/my-fpl-team');
		expect(oldAddress('#/efl-fantasy')).toBe('/efl-fantasy');
	});
	it('leave alone anything that isn\'t one of the old site\'s pages', () => {
		for (const h of ['', '#main', '#/nonsense', '#/club', '#advice', '#//evil.example', '#/clubs#x']) expect(oldAddress(h)).toBeNull();
	});
});

describe('menu', () => {
	it('names the section a page belongs to, for the stylesheet', () => {
		expect(tabFor('/')).toBe('home');
		expect(tabFor('/clubs')).toBe('table');
		expect(tabFor('/players')).toBe('table');
		expect(tabFor('/club/42/history')).toBe('club');
		expect(tabFor('/nation/England')).toBe('club');
		expect(tabFor('/simulation')).toBe('bets');
	});
	it('links every kind of page on this site', () => {
		expect(pageHref('club', 42)).toBe('/club/42');
		expect(pageHref('nation', "Côte d'Ivoire")).toBe("/nation/C%C3%B4te%20d'Ivoire");
	});
});
