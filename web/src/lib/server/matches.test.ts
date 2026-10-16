import { describe, expect, it } from 'vitest';
import type { Match } from '#lib/matches.ts';
import type { Site } from '#lib/site.ts';
import { cardView } from './matches';

const site = { teams: { 1: 'Burnley', 2: 'Wolves' }, competitions: {} } as unknown as Site;
const NOW = Date.parse('2026-10-16T21:05:00Z');
const match = (over: Partial<Match>): Match => ({
	id: 9, kickoff: '2026-10-17T14:00:00Z', league: 40, round: 'Round 11', home: 1, away: 2, status: 'NS',
	hg: null, ag: null, pen_h: null, pen_a: null, p_home: 0.27, p_draw: 0.29, p_away: 0.44,
	home_xg: null, away_xg: null, likely: null, home_rank: 848, away_rank: 925, source: null,
	home_xi: null, away_xi: null, home_missing: null, away_missing: null, ...over
} as Match);

describe("a match card's subscriber note", () => {
	it('shows on a match still to kick off, for a visitor behind the paywall', () => {
		expect(cardView(site, new Map(), match({}), true, NOW).lock).toBe('depth');
		expect(cardView(site, new Map(), match({ p_home: null, p_draw: null }), true, NOW).lock).toBe('chances');
	});
	it('goes once the match has kicked off, as the database sends it whole, even while the status still says not started', () => {
		const started = match({ kickoff: '2026-10-16T19:00:00Z', status: 'NS', home_xg: 1.0, away_xg: 1.4, likely: '1-1' });
		const card = cardView(site, new Map(), started, true, NOW);
		expect(card.lock).toBeNull();
		expect([card.homeXg, card.likely]).toEqual([1.0, '1-1']);
	});
	it('never shows for a subscriber, or with the paywall off', () => {
		expect(cardView(site, new Map(), match({}), false, NOW).lock).toBeNull();
	});
});
