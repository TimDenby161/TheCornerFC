// A player's page, worked out from his row in the Players list and his own file (players/<id>):
// league seasons by club, his last 20 league appearances, his clubs and positions season by
// season. A visitor who isn't a subscriber gets the file with a locked player's ranks left out.
import { GROUP_OF, GROUP_SINGLE } from './playerFilters.ts';

export type PlayerDoc = {
	id: number; born: string | null; cut?: boolean;
	season_fields: string[]; seasons: (number | null)[][];
	match_fields: string[]; matches: (string | number | null)[][];
	spell_fields: string[]; spells: Record<string, (number | null)[][]>;
	positions: Record<string, [string, number][]>;
	injury: [number, string, string | null] | null; // [fixture, type, ban]
	teams: Record<string, string>;
};
export type SeasonLine = { season: number; team: number; league: number; apps: number; starts: number | null; minutes: number; goals: number | null; assists: number | null; yellow: number | null; red: number | null };
export type Appearance = { fixture: number; date: string; league: number; team: number; opponent: number; home: number; gf: number; ga: number; started: number; minutes: number; role: string | null; rank: number | null; goals: number; assists: number; yellow: number; red: number };
export type Spell = { team: number; minutes: number | null; club_rank: number | null; goals: number | null; assists: number | null };

const named = <T>(fields: string[], rows: unknown[][]) => rows.map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])) as T);
export const seasonLines = (doc: PlayerDoc | null) => (doc ? named<SeasonLine>(doc.season_fields, doc.seasons) : []);
export const appearances = (doc: PlayerDoc | null) => (doc ? named<Appearance>(doc.match_fields, doc.matches) : []);
export const spells = (doc: PlayerDoc | null, key: string) => (doc?.spells?.[key] ? named<Spell>(doc.spell_fields, doc.spells[key]) : []);

// ---- A season's lines added up, all his clubs (null where no line has the stat)
const SUM_KEYS = ['apps', 'starts', 'minutes', 'goals', 'assists', 'yellow', 'red'] as const;
export type SeasonSum = Record<(typeof SUM_KEYS)[number], number | null>;
export function sumSeason(rows: SeasonLine[]): SeasonSum | null {
	if (!rows.length) return null;
	const out = {} as SeasonSum;
	for (const k of SUM_KEYS) {
		const vs = rows.map((r) => r[k]).filter((v): v is number => v != null);
		out[k] = vs.length ? vs.reduce((a, b) => a + b, 0) : null;
	}
	return out;
}
// a stat as the Stats tab shows it: the total, or per 90 minutes
export const statText = (s: SeasonSum, k: keyof SeasonSum, per90: boolean) =>
	s[k] == null ? '–' : per90 && s.minutes ? ((s[k]! * 90) / s.minutes).toFixed(2) : s[k]!.toLocaleString('en-GB');

// ---- Positions
const NO_ROLE = new Set(['G', 'D', 'M', 'F', 'SUB']); // a start without a line-up position, or off the bench
export const POS_WORD: Record<string, string> = { G: 'GK', D: 'DEF', M: 'MID', F: 'FWD', SUB: 'Sub' };
// The group a season is rated as: the role group with most starting minutes that season (as the
// model does); starts without a line-up position only if there's nothing else
export function seasonGroup(list: [string, number][] | undefined): string | null {
	const by = new Map<string, number>();
	for (const [r, m] of list || []) if (!NO_ROLE.has(r) && GROUP_OF[r]) by.set(GROUP_OF[r], (by.get(GROUP_OF[r]) || 0) + m);
	if (!by.size) for (const [r, m] of list || []) if (GROUP_OF[r]) by.set(GROUP_OF[r], (by.get(GROUP_OF[r]) || 0) + m);
	return by.size ? [...by].sort((a, b) => b[1] - a[1])[0][0] : null;
}
// [[role, minutes], ...] -> [["LB", 84], ["LWB", 16]]: shares of his starting minutes (minutes
// off the bench have no position and aren't counted; positions under 3% grouped as "other")
export function positionShares(list: [string, number][]): { label: string; pct: number; other: boolean }[] {
	list = list.filter(([r]) => r !== 'SUB');
	const total = list.reduce((a, [, m]) => a + m, 0);
	if (!total) return [];
	const shown = list.filter(([, m]) => m / total >= 0.03);
	const other = total - shown.reduce((a, [, m]) => a + m, 0);
	return [
		...shown.map(([r, m]) => ({ label: POS_WORD[r] || r, pct: Math.round((100 * m) / total), other: false })),
		...(other > 0 ? [{ label: 'other', pct: Math.round((100 * other) / total), other: true }] : [])
	];
}
// His positions in a row, most played first (his share of starting minutes over 12 months, else
// all time; then best rank): his rank in each role group he has one in, and his share there.
// Keepers have no position ranks: their keeper rank is their rank.
const GROUPS = ['GK', 'CB', 'FB', 'WB', 'DM', 'CM', 'AM', 'W', 'ST'];
export function positionChips(position: string | null, rank: number | null, ranks: Record<string, number> | null, positions: PlayerDoc['positions'] | undefined) {
	const group = position ? GROUP_OF[position] : null;
	const rankIn = (g: string) => ranks?.[g] ?? (g === group ? rank : null);
	const ranked = GROUPS.filter((g) => rankIn(g) != null);
	const rows = ((positions?.['12m'] ? positions['12m'] : positions?.all) || []).filter(([r]) => r !== 'SUB');
	const total = rows.reduce((a, [, m]) => a + m, 0);
	const mins: Record<string, number> = {};
	for (const [r, m] of rows) if (GROUP_OF[r]) mins[GROUP_OF[r]] = (mins[GROUP_OF[r]] || 0) + m;
	return ranked.sort((a, b) => (mins[b] || 0) - (mins[a] || 0) || rankIn(b)! - rankIn(a)!).map((g) => ({
		group: g, name: GROUP_SINGLE[g], rank: rankIn(g)!, pct: total ? Math.round((100 * (mins[g] || 0)) / total) : 0, main: g === group
	}));
}

// ---- The season rank chart: points oldest first, and where they sit in a box of the width given
export type ChartPoint = { label: string; season: string; v: number; est: boolean };
export function niceTicks(lo: number, hi: number, count: number): number[] {
	const step0 = (hi - lo) / count;
	const mag = Math.pow(10, Math.floor(Math.log10(step0)));
	const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
	const out = [];
	for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
	return out;
}
export function chartLayout(pts: ChartPoint[], width: number) {
	const W = Math.max(260, width), H = 180, L = 30, R = 14, T = 20, B = 22, IN = 12;
	let lo = Math.min(...pts.map((d) => d.v)), hi = Math.max(...pts.map((d) => d.v));
	const pad = Math.max(3, (hi - lo) * 0.15);
	lo = Math.max(0, lo - pad); hi = Math.min(100, hi + pad);
	const x = (i: number) => L + IN + (pts.length === 1 ? 0.5 : i / (pts.length - 1)) * (W - L - R - 2 * IN);
	const y = (v: number) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
	const every = Math.max(1, Math.ceil((pts.length * 46) / (W - L - R))); // x labels that fit
	return {
		W, H, L, R, T, B, x, y, ticks: niceTicks(lo, hi, 4),
		showLabel: (i: number) => i === pts.length - 1 || (i % every === 0 && pts.length - 1 - i >= every),
		path: pts.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join('')
	};
}
