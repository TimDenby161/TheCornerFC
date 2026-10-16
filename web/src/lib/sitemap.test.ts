import { describe, expect, it } from 'vitest';
import { MAIN_PAGES, sitemap } from './sitemap';

describe('the sitemap', () => {
	const xml = sitemap('https://thecornerfc.com', [{ team: 42, league: 39 }, { team: 7, league: 39 }, { team: 9, league: 140 }]);
	const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
	it('lists the main pages, each league once and each club, at the live address', () => {
		expect(locs.slice(0, MAIN_PAGES.length)).toEqual(MAIN_PAGES.map((p) => 'https://thecornerfc.com' + p));
		expect(locs.slice(MAIN_PAGES.length)).toEqual([
			'https://thecornerfc.com/league/39', 'https://thecornerfc.com/league/140',
			'https://thecornerfc.com/club/7', 'https://thecornerfc.com/club/9', 'https://thecornerfc.com/club/42'
		]);
	});
	it('is a sitemaps.org urlset', () => {
		expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')).toBe(true);
		expect(xml.trimEnd().endsWith('</urlset>')).toBe(true);
	});
	it('never lists the private pages', () => {
		for (const p of ['/account', '/admin', '/fpl', '/my-fpl-team', '/efl-fantasy']) expect(locs.some((l) => l.endsWith(p))).toBe(false);
	});
});
