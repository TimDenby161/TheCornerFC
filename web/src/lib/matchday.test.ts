import { describe, expect, it } from 'vitest';
import { addDays, compCountries, dayName, dayStart, daysWith, defaultDay, filterComps, goalsText, isDay, knownMatchFilter, localDay, matchRounds, pickRound, reasonText, roundDates, shownProbs, signedGoals, singleComp, TZ_OFF, validZone, zoneChoice, type MatchDays } from './matchday';
import type { Match } from './matches';
import type { Site } from './site';

describe('days in a time zone', () => {
	it('knows a real zone from a made-up one', () => {
		expect(validZone('Europe/London')).toBe(true);
		expect(validZone('America/New_York')).toBe(true);
		for (const tz of ['Mars/Olympus', '', null, undefined, 'x'.repeat(80)]) expect(validZone(tz)).toBe(false);
	});
	it('reads the time zone cookie: a zone, UK time chosen, or nothing yet', () => {
		expect(zoneChoice('America/New_York')).toEqual({ tz: 'America/New_York', ukTime: false });
		expect(zoneChoice(TZ_OFF)).toEqual({ tz: 'Europe/London', ukTime: true });
		for (const c of [undefined, '', 'Mars/Olympus']) expect(zoneChoice(c)).toEqual({ tz: 'Europe/London', ukTime: false });
	});
	it('puts a late kick-off on the right day for the visitor', () => {
		expect(localDay('2026-10-10T23:30:00+00:00', 'Europe/London')).toBe('2026-10-11'); // summer time
		expect(localDay('2026-10-10T23:30:00+00:00', 'America/New_York')).toBe('2026-10-10');
		expect(localDay('2026-10-10T02:00:00+00:00', 'America/Los_Angeles')).toBe('2026-10-09');
	});
	it('finds when a day starts there, through the clocks changing', () => {
		expect(dayStart('2026-10-10', 'Europe/London').toISOString()).toBe('2026-10-09T23:00:00.000Z');
		expect(dayStart('2026-12-10', 'Europe/London').toISOString()).toBe('2026-12-10T00:00:00.000Z');
		expect(dayStart('2026-10-25', 'Europe/London').toISOString()).toBe('2026-10-24T23:00:00.000Z'); // clocks go back that night
		expect(dayStart('2026-10-26', 'Europe/London').toISOString()).toBe('2026-10-26T00:00:00.000Z');
		expect(dayStart('2026-10-10', 'Asia/Tokyo').toISOString()).toBe('2026-10-09T15:00:00.000Z');
		expect(dayStart('2026-10-10', 'America/New_York').toISOString()).toBe('2026-10-10T04:00:00.000Z');
	});
	it('steps and names days', () => {
		expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
		expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
		expect(dayName('2026-10-10')).toBe('Sat 10 Oct');
		expect(isDay('2026-10-10')).toBe(true);
		for (const d of [null, '', '2026-13-45', '10/10/2026', "2026-10-10'"]) expect(isDay(d)).toBe(false);
	});
});

const md: MatchDays = { days: [['2026-10-08', 39, 2], ['2026-10-10', 39, 5], ['2026-10-10', 78, 3], ['2026-10-12', 5, 4]], leagues: [39, 78, 5], intl: [[5, 4]] };
describe('days with matches', () => {
	it('opens on today when something is on, else the next day that has matches, else the last', () => {
		expect(defaultDay(md, '2026-10-10')).toBe('2026-10-10');
		expect(defaultDay(md, '2026-10-09')).toBe('2026-10-10');
		expect(defaultDay(md, '2026-11-01')).toBe('2026-10-12');
	});
	it('lists the days for some competitions only', () => {
		expect(daysWith(md, [78])).toEqual(['2026-10-10']);
		expect(daysWith(md, null)).toEqual(['2026-10-08', '2026-10-10', '2026-10-12']);
	});
});

const site = { competitions: {
	2: { name: 'UEFA Champions League', country: 'World', type: 'Cup' }, 5: { name: 'UEFA Nations League', country: 'World', type: 'International' },
	39: { name: 'Premier League', country: 'England', type: 'League' }, 45: { name: 'FA Cup', country: 'England', type: 'Cup' },
	40: { name: 'Championship', country: 'England', type: 'League' }, 113: { name: 'Allsvenskan', country: 'Sweden', type: 'League' }
} } as unknown as Site;
describe('the competition menu', () => {
	const countries = compCountries(site, [45, 40, 39, 113, 2, 5, 9999]);
	it('puts leagues before cups under each country, and leaves international competitions out', () => {
		expect(countries.map((c) => [c.name, c.leagues, c.region])).toEqual([['England', [39, 40, 45], null], ['Sweden', [113], 'Scandinavia']]);
	});
	it('knows its own choices', () => {
		for (const f of ['all', '39', 'c:England', 'r:Scandinavia', 'e:all', 'e:2', 'i:all', 'i:5']) expect(knownMatchFilter(f, site, countries)).toBe(true);
		for (const f of [null, '777', 'c:Narnia', 'k:45', 'e:777', 'x']) expect(knownMatchFilter(f, site, countries)).toBe(false);
	});
	it('turns a choice into competitions', () => {
		expect(filterComps('all', countries, [5])).toBeNull();
		expect(filterComps('c:England', countries, [5])).toEqual([39, 40, 45]);
		expect(filterComps('i:all', countries, [5])).toEqual([5]);
		expect(filterComps('e:2', countries, [5])).toEqual([2]);
	});
	it('goes a round at a time for one competition only', () => {
		expect(singleComp('39')).toBe(39);
		expect(singleComp('e:2')).toBe(2);
		expect(singleComp('i:5')).toBe(5);
		for (const f of ['all', 'c:England', 'e:all', 'r:Scandinavia']) expect(singleComp(f)).toBeNull();
	});
});

const match = (id: number, kickoff: string, round: string | null, status = 'NS'): Match => ({ id, kickoff, round, status, league: 39, home: 1, away: 2 } as Match);
describe('rounds', () => {
	const rounds = matchRounds([
		match(1, '2026-10-03T14:00:00+00:00', 'Regular Season - 7', 'FT'), match(2, '2026-10-04T14:00:00+00:00', 'Regular Season - 7', 'FT'),
		match(3, '2026-11-20T19:00:00+00:00', 'Regular Season - 7'), // rearranged: outside its round's window
		match(4, '2026-10-17T14:00:00+00:00', 'Regular Season - 8'), match(5, '2026-10-18T14:00:00+00:00', 'Regular Season - 8', 'PST'),
		match(6, '2026-10-24T14:00:00+00:00', 'Regular Season - 9')
	], 'Europe/London');
	it('are in date order, named, with their scheduled dates', () => {
		expect(rounds.map((r) => r.label)).toEqual(['Round 7', 'Round 8', 'Round 9']);
		expect(roundDates(rounds[0], 'Europe/London')).toBe('3 Oct – 4 Oct');
		expect(roundDates(rounds[2], 'Europe/London')).toBe('24 Oct');
	});
	it('leave a postponed match out, and don\'t wait for a rearranged one', () => {
		expect(rounds[1].matches.map((m) => m.id)).toEqual([4]);
		expect(rounds[0].pending).toBe(false);
		expect(rounds[1].pending).toBe(true);
	});
	it('open on the round on now or next up, or the one on a day asked for', () => {
		expect(pickRound(rounds, null, 'Europe/London')!.label).toBe('Round 8');
		expect(pickRound(rounds, '2026-10-04', 'Europe/London')!.label).toBe('Round 7');
		expect(pickRound(rounds, '2026-10-20', 'Europe/London')!.label).toBe('Round 9');
		expect(pickRound(rounds, '2027-01-01', 'Europe/London')!.label).toBe('Round 8');
		expect(pickRound([], null, 'Europe/London')).toBeNull();
	});
	it('take a group stage a week at a time', () => {
		const g = matchRounds([match(1, '2026-09-15T19:00:00+00:00', 'Group A - 1'), match(2, '2026-09-17T19:00:00+00:00', 'Group B - 1'), match(3, '2026-09-29T19:00:00+00:00', 'Group A - 2')], 'Europe/London');
		expect(g.map((r) => [r.key, r.label, r.matches.length])).toEqual([['w:2026-09-14', 'Group stage', 2], ['w:2026-09-28', 'Group stage', 1]]);
	});
});

describe('a card\'s figures', () => {
	it('shows chances as whole percentages that add up to 100', () => {
		expect(shownProbs(0.335, 0.335)).toEqual([34, 34, 32]);
		expect(shownProbs(0.62, 0.213).reduce((a, b) => a + b)).toBe(100);
	});
	it('never calls something the model counted nothing', () => {
		expect(goalsText(0.02)).toBe('<0.1');
		expect(goalsText(0)).toBe('0');
		expect(signedGoals(-0.34)).toBe('−0.3');
		expect(signedGoals(0.01)).toBe('≈0');
	});
	it('puts a reason in words for the side it favours', () => {
		expect(reasonText('strength', 0.8, 'Arsenal', 'Leeds')).toEqual({ text: 'Arsenal rated the stronger side', size: '0.8 goals' });
		expect(reasonText('absences', -0.2, 'Arsenal', 'Leeds')).toEqual({ text: "More of Arsenal's regulars listed as missing", size: '0.2 goals' });
		expect(reasonText('tendencies', -0.3, 'A', 'B')!.text).toMatch(/tight/);
		expect(reasonText('unknown', 1, 'A', 'B')).toBeNull();
	});
});
