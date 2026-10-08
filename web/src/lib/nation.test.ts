import { describe, expect, it } from 'vitest';
import { nationFor, nationPlayers, nationPredictedXi, nationShape, nationSpell, nationTier, overviewPitch, readTeam, spellLabel, type Listed, type NationDoc, type NationsDoc } from './nation';

const ranking = { latest_match: '2026-10-06', matches: 3, aliases: { 'South Korea': ['Korea Republic'] },
	nations: [{ name: 'Spain', current: 1400 }, { name: 'England', current: 1361 }, { name: 'South Korea', current: 1100 }, { name: 'Malta', current: 700 }] } as unknown as NationsDoc;
describe('the ranking', () => {
	it('finds a nation by its own name or the feed\'s', () => {
		expect(nationFor(ranking, 'Korea Republic')?.name).toBe('South Korea');
		expect(nationFor(ranking, 'England')?.name).toBe('England');
		expect(nationFor(ranking, 'Atlantis')).toBeUndefined();
	});
	it('colours a rating by its place among the nations', () => {
		expect(nationTier(ranking, 1400)).toBe(2); // 1st of 4: the top 25%
		expect(nationTier(ranking, 700)).toBe(1);
	});
});

// two friendlies under an old coach, then three matches in a 4-3-3 under the current one
const XI = ['GK', 'RB', 'CB', 'CB', 'LB', 'DM', 'CM', 'CM', 'RW', 'LW', 'ST'];
const sheet = (match: number, players: number[]) => players.map((p, i) => [match, p, 90, 1, XI[i], i === 10 ? 1 : null, null, 0, 0]);
const eleven = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
const doc: NationDoc = {
	id: 10, name: 'England', coach: { id: 40, name: 'T. Tuchel', since: '2025-01-01' },
	match_fields: ['date', 'opp', 'venue', 'gf', 'ga', 'tournament', 'formation', 'coach', 'coach_id'],
	matches: [
		['2024-10-10', 'Greece', 'H', 1, 2, 'UEFA Nations League', '4-2-3-1', 'L. Carsley', 39],
		['2025-03-21', 'Albania', 'H', 2, 0, 'World Cup - Qualification', '4-3-3', 'T. Tuchel', 40],
		['2025-06-07', 'Andorra', 'A', 1, 0, 'World Cup - Qualification', '4-3-3', 'T. Tuchel', 40],
		['2026-10-06', 'Czechia', 'H', 3, 0, 'UEFA Nations League', '4-3-3', 'T. Tuchel', 40]
	],
	app_fields: ['match', 'player', 'minutes', 'started', 'role', 'goals', 'assists', 'yellow', 'red'],
	apps: [
		...sheet(0, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20]),
		...sheet(1, eleven), ...sheet(2, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]), ...sheet(3, eleven),
		[3, 12, 20, 0, null, 1, null, 1, 0], [3, 13, null, 0, null, null, null, 0, 1]
	],
	players: { 1: 'J. Pickford', 11: 'H. Kane', 12: 'O. Watkins', 13: 'N. O&apos;Reilly', 20: 'Old Striker' }
};
const team = readTeam(doc);

describe('a nation\'s file', () => {
	it('gives each match the eleven that started, and reads encoded names', () => {
		expect(team.matches[3].xi).toHaveLength(11);
		expect(team.players[13]).toBe("N. O'Reilly");
	});
	it('takes the current coach\'s matches from his start date', () => {
		const spell = nationSpell(team);
		expect(spell).toMatchObject({ coach: 'T. Tuchel', since: '2025-01-01', full: true });
		expect(spell.rows.map((m) => m.date)).toEqual(['2025-03-21', '2025-06-07', '2026-10-06']);
		expect(spellLabel(spell)).toBe('Under T. Tuchel');
	});
	it('falls back to his unbroken spell on the team sheets when no start date is known', () => {
		const spell = nationSpell({ ...team, coach: null });
		expect(spell.coach).toBe('T. Tuchel');
		expect(spell.rows).toHaveLength(3);
	});
});

describe('the predicted XI', () => {
	it('uses the coach\'s most used formation, as his latest XI in it', () => {
		const shape = nationShape(team)!;
		expect(shape.formation).toBe('4-3-3');
		expect(shape.need.get('CB')).toBe(2);
		expect(shape.need.get('CM')).toBe(2);
	});
	it('gives each position to whoever started there most, recent matches counting more', () => {
		const pred = nationPredictedXi(team, new Set())!;
		expect(pred.picks).toHaveLength(11);
		expect(pred.picks.find((p) => p.role === 'ST')!.pid).toBe(11);
		expect(pred.picks[0].role).toBe('GK');
	});
	it('leaves out a regular who is injured, and says so', () => {
		const pred = nationPredictedXi(team, new Set([11]))!;
		expect(pred.picks.find((p) => p.role === 'ST')!.pid).toBe(12);
		expect(pred.out).toEqual([11]);
	});
});

describe('the overview pitch', () => {
	const listed = (id: number, position: string, ord: number, rank: number | null = 80): Listed => ({ id, name: `Player ${id}`, rank, ord, position, team: 42 });
	const list = [listed(11, 'ST', 0), listed(50, 'ST', 1), listed(9, 'RW', 2), listed(60, 'AM', 3, null)];
	it('puts the best in each position of the usual shape, with everyone the coach has picked', () => {
		const pitch = overviewPitch(list, team);
		expect(pitch).toMatchObject({ formation: '4-3-3', coach: 'T. Tuchel', hasShape: true });
		const st = pitch.boxes.find((b) => b.label === 'ST')!;
		expect(st.players.map((x) => [x.p.id, x.unpicked])).toEqual([[11, false], [50, true], [12, false]]);
		expect(st.players[2].p).toMatchObject({ name: 'O. Watkins', listed: false, rank: null });
	});
	it('puts a player whose own position the shape lacks in the nearest it has', () => {
		const pitch = overviewPitch(list, team);
		expect(pitch.boxes.find((b) => b.label === 'CM')!.players.some((x) => x.p.id === 60)).toBe(true);
	});
	it('without line-ups, shows the top three in each of a fixed set of positions', () => {
		const pitch = overviewPitch(list, null);
		expect(pitch.hasShape).toBe(false);
		expect(pitch.boxes.map((b) => b.label)).toEqual(['GK', 'RB', 'CB', 'LB', 'DM', 'CM', 'RW', 'AM', 'LW', 'ST']);
		expect(pitch.boxes.find((b) => b.label === 'ST')!.players.map((x) => x.unpicked)).toEqual([false, false]);
	});
});

describe('players under the coach', () => {
	const players = nationPlayers(team, nationSpell(team), () => 'AM', 'minutes');
	const of = (id: number) => players.find((p) => p.id === id)!;
	it('adds up appearances, minutes and goals, and leaves the old coach\'s matches out', () => {
		expect(of(11)).toMatchObject({ apps: 2, minutes: 180, goals: 2, role: 'ST', last: '2026-10-06' });
		expect(players.some((p) => p.id === 20)).toBe(false);
	});
	it('counts a match with no stat line as one whose minutes aren\'t known, and falls back to his club position', () => {
		expect(of(13)).toMatchObject({ apps: 1, minutes: 0, noMins: 1, r: 1, cards: 3, role: 'AM' });
		expect(of(12)).toMatchObject({ apps: 2, minutes: 110, y: 1 });
	});
	it('sorts by the column asked for', () => {
		expect(nationPlayers(team, nationSpell(team), () => null, 'cards')[0].id).toBe(13);
		expect(players[0].minutes).toBe(270);
	});
});
