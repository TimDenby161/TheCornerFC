import { describe, expect, it } from 'vitest';
import { clubDepth, predictedXi, squadStrength, xiSpots, type SquadPlayer } from './depth';
import { formationRoles } from './formations';

const player = (id: number, position: string, rank: number): SquadPlayer => ({ id, name: `P${id}`, position, rank, position_ranks: null, positions_12m: [position] });
const squad = [player(1, 'GK', 80), player(2, 'GK', 60), ...['RB', 'CB', 'CB', 'LB', 'CM', 'CM', 'AM', 'RW', 'LW', 'ST'].map((pos, i) => player(10 + i, pos, 85 - i)), player(30, 'ST', 70)];
// six matches in a 4-2-3-1 with the same eleven, in team-sheet order
const line = [1, 'GK', 10, 'RB', 11, 'CB', 12, 'CB', 13, 'LB', 14, 'DM', 15, 'DM', 16, 'AM', 17, 'RW', 18, 'LW', 19, 'ST'];
const starts = { games: 6, xi: Array.from({ length: 6 }, () => line), xi_league: Array(6).fill(39), xi_formation: Array(6).fill('4-2-3-1'),
	players: Object.fromEntries(Array.from({ length: 11 }, (_, i) => [String(line[2 * i]), { [line[2 * i + 1]]: 6 }])), mins: {}, mins_matches: 6 };
const depth = (out: number[] = []) => clubDepth({ squad, out: new Set(out), starts, seasonFormations: Array(6).fill('4-2-3-1'), nextGroup: 'league', groupOf: () => 'league' });

describe('formationRoles', () => {
	it('names the roles in a formation', () => {
		expect(formationRoles('4-2-3-1')).toEqual(['GK', 'LB', 'CB', 'RB', 'DM', 'LW', 'AM', 'RW', 'ST']);
		expect(formationRoles('3-5-2')).toEqual(['GK', 'CB', 'LWB', 'CM', 'RWB', 'ST']);
		expect(formationRoles('nonsense')).toEqual([]);
	});
});

describe('clubDepth', () => {
	it('has no squad without players', () => {
		expect(clubDepth({ squad: [], out: new Set(), seasonFormations: [], nextGroup: null, groupOf: () => 'league' })).toBeNull();
	});
	it('shows only the positions of the formations used, with their usual starters adding up to eleven', () => {
		const d = depth()!;
		expect(d.shown.map((b) => b.label).sort()).toEqual(['AM', 'CB', 'CM', 'GK', 'LB', 'LW', 'RB', 'RW', 'ST']);
		expect(d.shown.reduce((t, b) => t + b.n, 0)).toBe(11);
		expect(d.shown.find((b) => b.label === 'CB')!.n).toBe(2);
	});
	it('gives an ever-present nearly all the start chance, and a full box 90 minutes a starter', () => {
		const d = depth()!;
		expect(d.startChance.get('GK:1')).toBeGreaterThan(95);
		expect(d.startChance.get('GK:2')).toBeLessThan(5);
		expect(d.boxMins.get('CB')).toBe(180);
		for (const p of squad) expect(d.shown.reduce((t, b) => t + (d.xMins.get(`${b.label}:${p.id}`) || 0), 0)).toBeLessThanOrEqual(90);
	});
	it('hands an injured starter\'s share to whoever else plays there', () => {
		const d = depth([19])!; // the striker is out
		expect(d.shown.find((b) => b.label === 'ST')!.ps.map((x) => x.p.id)).toEqual([30]);
		expect(d.startChance.get('ST:30')).toBeGreaterThan(95);
	});
});

describe('the predicted XI', () => {
	const xi = predictedXi(depth())!;
	it('is eleven players, one position each', () => {
		expect(xi).toHaveLength(11);
		expect(new Set(xi.map((c) => c.p.id)).size).toBe(11);
		expect(xi.map((c) => c.p.id).sort((a, b) => a - b)).toEqual([1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
	});
	it('stands the keeper at the top and spreads two centre-backs apart', () => {
		const spots = xiSpots(xi);
		const gk = spots.find((s) => s.c.box.label === 'GK')!, cbs = spots.filter((s) => s.c.box.label === 'CB');
		expect(gk.y).toBeLessThan(cbs[0].y);
		expect(Math.abs(cbs[0].x - cbs[1].x)).toBeGreaterThanOrEqual(22);
	});
	it('keeps every pair of players on the same or neighbouring lines 22% apart, in every usual formation', () => {
		const shapes = ['4-4-2', '4-3-3', '4-2-3-1', '4-1-4-1', '4-4-1-1', '4-3-2-1', '4-1-2-1-2', '4-2-2-2', '4-3-1-2', '4-5-1', '3-4-3', '3-5-2', '3-4-2-1', '3-4-1-2', '3-1-4-2', '5-3-2', '5-4-1'];
		for (const shape of shapes) {
			const lines = shape.split('-').map(Number), last = lines.length - 1, roles = ['GK'];
			// each line's roles as positions.py names them
			const wide = (n: number, col: number, l: string, m: string, r: string) => (col === 1 ? l : col === n ? r : m);
			lines.forEach((n, idx) => {
				for (let col = 1; col <= n; col++) {
					if (idx === 0) roles.push(n === 4 ? wide(n, col, 'LB', 'CB', 'RB') : n === 5 ? wide(n, col, 'LWB', 'CB', 'RWB') : 'CB');
					else if (idx === last) roles.push(n >= 3 ? wide(n, col, 'LW', 'ST', 'RW') : 'ST');
					else if (last === 2 || idx === 1) roles.push(last !== 2 && n <= 2 ? 'DM' : n === 4 ? (lines[0] === 3 ? wide(n, col, 'LWB', 'CM', 'RWB') : wide(n, col, 'LM', 'CM', 'RM')) : n === 5 ? wide(n, col, 'LWB', 'CM', 'RWB') : 'CM');
					else roles.push(n <= 2 ? (idx === last - 1 ? 'AM' : 'CM') : n === 4 ? wide(n, col, 'LM', 'CM', 'RM') : wide(n, col, 'LW', 'AM', 'RW'));
				}
			});
			const spots = xiSpots(roles.map((label) => ({ box: { label } })));
			expect(spots, shape).toHaveLength(11);
			for (const a of spots) for (const b of spots) {
				if (a === b || Math.abs(a.y - b.y) >= 10) continue;
				expect(Math.abs(a.x - b.x), `${shape}: ${a.c.box.label} and ${b.c.box.label}`).toBeGreaterThanOrEqual(22);
				expect(a.x, `${shape}: ${a.c.box.label}`).toBeGreaterThanOrEqual(14);
				expect(a.x, `${shape}: ${a.c.box.label}`).toBeLessThanOrEqual(86);
			}
		}
	});
	it('rates the expected squad between its best and worst player', () => {
		const s = squadStrength(depth())!;
		expect(s.strength).toBeGreaterThan(60);
		expect(s.strength).toBeLessThan(86);
		expect(s.attack).not.toBeNull();
	});
});
