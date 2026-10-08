import { describe, expect, it } from 'vitest';
import { appearances, chartLayout, niceTicks, positionChips, positionShares, seasonGroup, seasonLines, spells, statText, sumSeason, type PlayerDoc } from './player';

const doc: PlayerDoc = {
	id: 1, born: '2000-07-21',
	season_fields: ['season', 'team', 'league', 'apps', 'starts', 'minutes', 'goals', 'assists', 'yellow', 'red'],
	seasons: [[2026, 50, 39, 5, 5, 450, 5, 0, 0, 0], [2025, 50, 39, 20, 18, 1700, 15, 4, 2, 0], [2025, 165, 78, 10, null, 800, 6, 2, 1, 0]],
	match_fields: ['fixture', 'date', 'league', 'team', 'opponent', 'home', 'gf', 'ga', 'started', 'minutes', 'role', 'rank', 'goals', 'assists', 'yellow', 'red'],
	matches: [[9, '2026-09-20', 39, 50, 746, 1, 5, 3, 1, 90, 'ST', 97.8, 1, 0, 0, 0]],
	spell_fields: ['team', 'minutes', 'club_rank', 'goals', 'assists'],
	spells: { '2025': [[50, 1700, 1090, 15, 4], [165, 800, 1033, 6, 2]], now: [[50, 1672, 1087, 13, 4]] },
	positions: { '12m': [['ST', 2000], ['LW', 500], ['SUB', 300]], all: [['ST', 15000]] },
	injury: null, teams: { 50: 'Manchester City' }
};

describe('reading his file', () => {
	it('names the figures by their fields', () => {
		expect(seasonLines(doc)[0]).toMatchObject({ season: 2026, team: 50, minutes: 450, goals: 5 });
		expect(appearances(doc)[0]).toMatchObject({ date: '2026-09-20', opponent: 746, role: 'ST', rank: 97.8 });
		expect(spells(doc, 'now')[0]).toMatchObject({ team: 50, club_rank: 1087 });
	});
	it('gives nothing for a player with no file, or a season he has no spell in', () => {
		expect(seasonLines(null)).toEqual([]);
		expect(appearances(null)).toEqual([]);
		expect(spells(doc, '1999')).toEqual([]);
	});
});

describe('sumSeason', () => {
	const s = sumSeason(seasonLines(doc).filter((r) => r.season === 2025))!;
	it('adds a season up over all his clubs', () => {
		expect(s).toMatchObject({ apps: 30, minutes: 2500, goals: 21, assists: 6, yellow: 3, red: 0 });
	});
	it('adds up what there is where a league gives no starts', () => {
		expect(s.starts).toBe(18);
		expect(sumSeason([])).toBeNull();
	});
	it('shows a stat as a total or per 90 minutes', () => {
		expect(statText(s, 'goals', false)).toBe('21');
		expect(statText(s, 'goals', true)).toBe('0.76');
		expect(statText({ ...s, red: null }, 'red', true)).toBe('–');
	});
});

describe('positions', () => {
	it('rates a season as the group he started most in, ignoring starts with no line-up position', () => {
		expect(seasonGroup([['LB', 900], ['RB', 800], ['CB', 1000]])).toBe('FB');
		expect(seasonGroup([['M', 2000], ['AM', 90]])).toBe('AM');
		expect(seasonGroup([['M', 2000]])).toBe('CM');
		expect(seasonGroup(undefined)).toBeNull();
	});
	it('shares out his starting minutes, small ones together, the bench left out', () => {
		expect(positionShares([['LB', 840], ['LWB', 140], ['CM', 20], ['SUB', 500]])).toEqual([
			{ label: 'LB', pct: 84, other: false }, { label: 'LWB', pct: 14, other: false }, { label: 'other', pct: 2, other: true }]);
		expect(positionShares([['SUB', 90]])).toEqual([]);
	});
	it('lists the groups he has a rank in, most played first', () => {
		const chips = positionChips('ST', 96.2, { W: 85, ST: 95.6 }, doc.positions);
		expect(chips.map((c) => [c.group, c.pct, c.main])).toEqual([['ST', 80, true], ['W', 20, false]]);
		expect(chips[0].rank).toBe(95.6);
	});
	it('gives a keeper his rank as his keeper rank, and a locked player nothing', () => {
		expect(positionChips('GK', 88, null, { all: [['GK', 900]] })).toMatchObject([{ group: 'GK', rank: 88, pct: 100 }]);
		expect(positionChips('CM', null, null, doc.positions)).toEqual([]);
	});
});

describe('the season rank chart', () => {
	const pts = [70, 80, 90].map((v, i) => ({ label: `2${i}/2${i + 1}`, season: '', v, est: false }));
	it('picks round ticks inside the range', () => {
		expect(niceTicks(67, 93, 4)).toEqual([70, 80, 90]);
	});
	it('spreads the points across the box, higher ranks higher up', () => {
		const c = chartLayout(pts, 600);
		expect(c.x(0)).toBeLessThan(c.x(2));
		expect(c.y(90)).toBeLessThan(c.y(70));
		expect(c.path.startsWith('M')).toBe(true);
		expect(c.showLabel(2)).toBe(true);
	});
	it('never draws narrower than 260', () => {
		expect(chartLayout(pts, 100).W).toBe(260);
	});
});
