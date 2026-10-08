import { describe, expect, it } from 'vitest';
import { clubHistory, clubMatches, clubMove, clubSeasons, formationDots, formationUse, leagueZones, personInitials, shortDate, longDate, shortName, wdl, type ClubDoc } from './club';

const fields = ['date', 'rank', 'opponent', 'home', 'gf', 'ga', 'league', 'formation'];
const doc = (matches: ClubDoc['matches']): ClubDoc => ({ id: 1, start: 1000, fields, matches, coach: null, colors: null, teams: {} });
const rows = clubMatches(doc([
	['2025-05-20', 1010, 2, 1, 2, 0, 39, '4-3-3'],
	['2025-08-16', 1004, 3, 0, 0, 1, 39, '4-3-3'],
	['2025-09-01', 1004, 4, 1, 1, 1, 45, null],
	['2025-12-26', 1020, 5, 1, 3, 0, 39, '4-2-3-1'],
	['2026-01-10', 1031, 6, 0, 2, 1, 39, '4-3-3']
]));

describe('clubMatches', () => {
	it('names each figure by its field, and gives nothing for a club with no file', () => {
		expect(rows[0]).toMatchObject({ date: '2025-05-20', rank: 1010, gf: 2, formation: '4-3-3' });
		expect(clubMatches(null)).toEqual([]);
	});
});

describe('clubMove', () => {
	it('is the change from the rating before, the file\'s start for the first match', () => {
		expect(clubMove(rows, 0, 1000)).toBe(10);
		expect(clubMove(rows, 1, 1000)).toBe(-6);
		expect(clubMove(rows, 0, null)).toBeNull();
	});
});

describe('clubSeasons', () => {
	it('runs July to June for a winter league', () => {
		const { seasonOf, label, calendar } = clubSeasons(rows);
		expect(calendar).toBe(false);
		expect(rows.map(seasonOf)).toEqual([2024, 2025, 2025, 2025, 2025]);
		expect(label(2025)).toBe('25/26');
	});
	it('is the calendar year for a club that plays through the summer', () => {
		const summer = clubMatches(doc([['2025-06-10', 1, 2, 1, 1, 0, 253, null], ['2025-07-10', 1, 2, 1, 1, 0, 253, null], ['2025-12-01', 1, 2, 1, 1, 0, 253, null]]));
		const { seasonOf, label } = clubSeasons(summer);
		expect(summer.map(seasonOf)).toEqual([2025, 2025, 2025]);
		expect(label(2025)).toBe('2025');
	});
});

describe('clubHistory', () => {
	const seasons = clubHistory(rows, 1000, (lg) => lg === 45);
	it('lists seasons newest first with record, goals and rating', () => {
		expect(seasons.map((s) => s.label)).toEqual(['25/26', '24/25']);
		expect(seasons[0]).toMatchObject({ played: 4, w: 2, d: 1, l: 1, gf: 6, ga: 3, start: 1010, end: 1031, peak: 1031, league: 39 });
		expect(seasons[1]).toMatchObject({ played: 1, start: 1000, end: 1010 });
	});
	it('has no league for a season of cup matches only', () => {
		expect(clubHistory(rows.slice(2, 3), null, () => true)[0].league).toBeNull();
	});
});

describe('formationUse', () => {
	it('puts the most used first, with share, record and last use', () => {
		const use = formationUse(rows.filter((m) => m.formation));
		expect(use.map((u) => u.formation)).toEqual(['4-3-3', '4-2-3-1']);
		expect(use[0]).toMatchObject({ matches: 3, share: 75, record: '2W 0D 1L', gf: 4, ga: 2, last: '2026-01-10' });
	});
});

describe('formationDots', () => {
	it('is a keeper and one dot a player', () => {
		expect(formationDots('4-2-3-1')).toHaveLength(11);
		expect(formationDots('4-4-2')[0]).toEqual([30, 9]);
		expect(formationDots('nonsense')).toEqual([]);
	});
});

describe('leagueZones', () => {
	it('gives each note a class in order, relegation its own', () => {
		const z = leagueZones([{ description: 'Champions League' }, { description: 'Champions League' }, { description: 'Europa League' }, { description: null }, { description: 'Relegation play-off' }, { description: 'Relegation' }]);
		expect([...z.values()]).toEqual(['zone-0', 'zone-1', 'zone-down', 'zone-down2']);
	});
});

describe('names and dates', () => {
	it('shortens a name to the surname, keeping particles', () => {
		expect(shortName('E. Haaland')).toBe('Haaland');
		expect(shortName('V. van Dijk')).toBe('van Dijk');
		expect(shortName('Gabriel Magalhães')).toBe('Gabriel');
	});
	it('takes first and last initials', () => {
		expect(personInitials('Mikel Arteta')).toBe('MA');
		expect(personInitials('Rodri')).toBe('R');
	});
	it('writes a match day without a time zone', () => {
		expect(shortDate('2026-09-05')).toBe('5 Sep');
		expect(longDate('2019-12-01')).toBe('1 Dec 2019');
	});
	it('counts a record', () => {
		expect(wdl(rows)).toBe('3W 1D 1L');
	});
});
