// The Players table's side filters: the ranges (Ability, club world rank, minutes) and age as
// two-handled sliders, the position pitch, and the club and nationality picks.
import type { Country } from './clubTable.ts';
import { leagueName, teamName, type Site } from './site.ts';

// ---- A range as the address has it: "20-25", "-25" (up to), "20-" (from); null = that end open
export type Range = [number | null, number | null];
export function parseRange(text: string | null): Range {
	const m = (text || '').match(/^(\d*(?:\.\d+)?)-(\d*(?:\.\d+)?)$/);
	return m ? [m[1] === '' ? null : Number(m[1]), m[2] === '' ? null : Number(m[2])] : [null, null];
}
export const rangeText = ([lo, hi]: Range) => (lo == null && hi == null ? null : `${lo ?? ''}-${hi ?? ''}`);
export const rangeOn = (r: Range) => r[0] != null || r[1] != null;

export const RANGES = {
	ab: { label: 'Ability', tip: "Underlying Ability, 0-100: the model's estimate of his level now" },
	crank: { label: 'Club world rank', tip: "His club's place among every ranked club by Baseline Strength (1 = strongest). Players without a ranked club drop out while this is set" },
	mins: { label: 'Minutes', tip: 'Minutes over his last 20 appearances, the evidence behind his Ability' }
} as const;
export type RangeKey = keyof typeof RANGES | 'age';
export type PlayerFacets = {
	players: number; age: [number, number] | null; ability: [number, number] | null; minutes: number;
	positions: Record<string, number>; clubs: [number, number][]; nats: string[];
};

// Each slider moves over a list of stops: every age and every whole Ability from the lowest to the
// highest, minutes a match (90) at a time, and club ranks finer at the top (1, 5, 10, 20 ...) so
// the top 50 can be picked out of thousands. A handle at either end leaves that end open.
export function rangeStops(k: RangeKey, facets: PlayerFacets, rankedClubs: number): number[] {
	const span = ([lo, hi]: [number, number]) => Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
	if (k === 'age') return span(facets.age || [15, 45]);
	if (k === 'ab') return span(facets.ability || [0, 0]);
	if (k === 'mins') return Array.from({ length: Math.ceil(facets.minutes / 90) + 1 }, (_, i) => i * 90);
	const n = rankedClubs;
	return [...[1, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 750].filter((x) => x < n),
		...Array.from({ length: Math.max(0, Math.ceil(n / 500) - 1) }, (_, i) => (i + 2) * 500).filter((x) => x < n), n];
}
// a handle's stop for a range end (one from a link needn't be on a stop: the nearest stop inside it)
export function stopIndex(stops: number[], v: number | null, end: 0 | 1): number {
	const n = stops.length - 1;
	if (v == null) return end ? n : 0;
	const i = end ? stops.findLastIndex((s) => s <= v) : stops.findIndex((s) => s >= v);
	return i < 0 ? (end ? 0 : n) : i;
}
// the range two handles stand for, and what the slider says beside its name
export const handlesRange = (stops: number[], a: number, b: number): Range => [a <= 0 ? null : stops[a], b >= stops.length - 1 ? null : stops[b]];
export function rangeLabel(k: RangeKey, stops: number[], a: number, b: number): string {
	const n = stops.length - 1, fmt = (v: number) => v.toLocaleString('en-GB');
	if (k === 'age') return a === 0 && b === n ? 'All ages' : a === b ? `${stops[a]}` : `${stops[a]}–${stops[b]}`;
	if (a === 0 && b === n) return 'All';
	if (a === 0) return k === 'crank' ? `Top ${fmt(stops[b])}` : `Up to ${fmt(stops[b])}`;
	if (b === n) return `${fmt(stops[a])}${k === 'crank' ? ' down' : '+'}`;
	return `${fmt(stops[a])}–${fmt(stops[b])}`;
}
// for the database: whole numbers, an open end as null
export const rangeParam = ([lo, hi]: Range) => [lo == null ? null : Math.ceil(lo), hi == null ? null : Math.floor(hi)];

// ---- Position: a pitch of positions, attacking upwards. [position, x %, y %]
export const PITCH_SPOTS: [string, number, number][] = [
	['ST', 50, 12],
	['LW', 18, 25], ['AM', 50, 27], ['RW', 82, 25],
	['LM', 18, 41], ['CM', 50, 43], ['RM', 82, 41],
	['LWB', 18, 57], ['DM', 50, 57], ['RWB', 82, 57],
	['LB', 18, 72], ['CB', 50, 73], ['RB', 82, 72],
	['GK', 50, 89]
];
export const isPosition = (p: string) => PITCH_SPOTS.some(([s]) => s === p);
// the role group each position is rated in (as positions.py)
export const GROUP_OF: Record<string, string> = {
	GK: 'GK', CB: 'CB', LB: 'FB', RB: 'FB', LWB: 'WB', RWB: 'WB', DM: 'DM', CM: 'CM', LM: 'W', RM: 'W',
	AM: 'AM', LW: 'W', RW: 'W', ST: 'ST', G: 'GK', D: 'CB', M: 'CM', F: 'ST'
};
export const GROUP_SINGLE: Record<string, string> = {
	GK: 'goalkeeper', CB: 'centre-back', FB: 'full-back', WB: 'wing-back', DM: 'defensive mid', CM: 'central mid',
	AM: 'attacking mid', W: 'winger', ST: 'striker'
};
// With the position filter on: the selected role groups, and a player's rank as the best of them
// (how good he is in each position he has started in, less for one he rarely plays)
export const selectedGroups = (positions: string[]) => [...new Set(positions.map((r) => GROUP_OF[r]).filter(Boolean))];
export function posRank(ranks: Record<string, number> | null | undefined, groups: string[]): number | null {
	const v = groups.map((g) => ranks?.[g]).filter((x): x is number => x != null);
	return v.length ? Math.max(...v) : null;
}

// ---- Club and nationality: pick one or more of each. What the two boxes list: clubs (the league
// added to a name two clubs share), the same clubs under their leagues in the competition menu's
// order, and the nationalities; each with a key for accent-free matching.
export const whoKey = (s: string) => s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
export type WhoClub = { id: number; name: string; league: number; key: string };
export type WhoOptions = {
	clubs: WhoClub[];
	leagues: { id: number; name: string; country: string | null; clubs: number[] }[];
	nats: { name: string; key: string }[];
};
export function whoOptions(site: Site, facets: PlayerFacets, countries: Country[]): WhoOptions {
	const names = new Map<string, number>();
	for (const [t] of facets.clubs) { const n = teamName(site, t); names.set(n, (names.get(n) || 0) + 1); }
	const clubs = facets.clubs.map(([id, lg]) => {
		const n = teamName(site, id), name = names.get(n)! > 1 ? `${n} (${leagueName(site, lg)})` : n;
		return { id, name, league: lg, key: whoKey(name) };
	}).sort((a, b) => a.name.localeCompare(b.name));
	const order = countries.flatMap((c) => c.leagues);
	const pos = (lg: number) => { const i = order.indexOf(lg); return i === -1 ? order.length : i; };
	const byLeague = new Map<number, number[]>();
	for (const c of clubs) byLeague.set(c.league, [...(byLeague.get(c.league) || []), c.id]);
	return {
		clubs,
		leagues: [...byLeague].map(([id, list]) => ({ id, name: leagueName(site, id), country: site.competitions[id]?.country ?? null, clubs: list }))
			.sort((a, b) => pos(a.id) - pos(b.id) || a.name.localeCompare(b.name)),
		nats: facets.nats.slice().sort((a, b) => a.localeCompare(b)).map((name) => ({ name, key: whoKey(name) }))
	};
}
// Typing in a box: whatever has the text anywhere in its name, starts of names first
export function whoMatches<T extends { key: string; name: string }>(items: T[], q: string, max = 60): T[] {
	const rank = (k: string) => (k.startsWith(q) ? 0 : k.includes(` ${q}`) || k.includes(`-${q}`) ? 1 : 2);
	return items.filter((x) => x.key.includes(q)).map((x) => [rank(x.key), x] as const)
		.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).slice(0, max).map(([, x]) => x);
}
