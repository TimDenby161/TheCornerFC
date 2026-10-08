// The three fantasy pages (FPL, My FPL team, EFL Fantasy), shown to the site owner only: FPL's and
// Fantasy EFL's terms don't allow their data to be republished or used commercially, so it is
// never in a page the server writes. The browser asks for it (/fantasy/data), the database
// answers only the owner, and everything here is worked out from that answer in the browser.
import { decodeEntities } from './players.ts';

export const FPL_ENTRY = 3996593; // the owner's FPL entry
export const FPL_POS: Record<string, string> = { G: 'GK', D: 'DEF', M: 'MID', F: 'FWD' };
export const FPL_STATUS: Record<string, string> = { i: 'Injured', s: 'Suspended', u: 'Unavailable', n: 'Not in squad' };
export const FPL_SHOWN = 30, EFL_SHOWN = 30;
// Where a player's points come from (part_fields in the predictions)
export const FPL_PARTS: Record<string, string> = {
	appearance: 'Minutes', goal: 'Goals', penalty: 'Penalties', assist: 'Assists', fpl_assist: 'FPL assists',
	clean_sheet: 'Clean sheet', goals_conceded: 'Goals conceded', save: 'Saves', penalty_save: 'Penalty saves', card: 'Cards', bonus: 'Bonus',
	dc: 'Defensive contributions'
};
export const EFL_PARTS: Record<string, string> = {
	appearance: 'Minutes', goal: 'Goals', hat_trick: 'Hat-trick', assist: 'Assists', penalty_miss: 'Penalty misses',
	clean_sheet: 'Clean sheet', goals_conceded: 'Goals conceded', save: 'Saves', penalty_save: 'Penalty saves', card: 'Cards',
	tackle: 'Tackles', block: 'Blocks', clearance: 'Clearances', interception: 'Interceptions', key_pass: 'Key passes',
	shot_on_target: 'Shots on target'
};
export const EFL_CLUB_PARTS: Record<string, string> = { win: 'Win', draw: 'Draw', away_win: 'Away win', clean_sheet: 'Clean sheet', goals_2: '2+ goals', goals_4: '4+ goals' };
export const EFL_LEAGUE_SHORT: Record<number, string> = { 40: 'Champ', 41: 'L1', 42: 'L2' };
export const EFL_FORMATIONS = [[2, 2, 2], [2, 3, 1], [3, 2, 1]]; // DEF-MID-FWD behind one goalkeeper
export const CHIP_NAMES: Record<string, string> = { wildcard: 'Wildcard', freehit: 'Free Hit', bboost: 'Bench Boost', '3xc': 'Triple Captain' };
export const CHIP_GAIN: Record<string, string> = {
	wildcard: "over the plan's weeks, against the plan", freehit: 'that week, against the planned squad',
	bboost: 'from the bench', '3xc': 'from the extra captaincy'
};

// ---- what the database sends
export type Gameweek = { id: number; first_kickoff: string; started?: boolean; start?: string; end?: string };
// Players and their matches come as rows of values, named by `fields` and `cell_fields`
export type PredDoc = {
	source?: string; model: string; gameweeks: Gameweek[]; teams: Record<string, [string, string, number?]>;
	fields: string[]; cell_fields: string[]; part_fields?: string[]; players: unknown[][]; cells: unknown[][][];
	// EFL Fantasy only: the divisions' names, and each club's own points by match
	leagues?: Record<string, string>; clubs?: Record<string, unknown[][]>; club_fields?: string[]; club_part_fields?: string[];
};
export type Chip = { name: string; start: number; stop: number; played: number | null };
export type TeamDoc = {
	entry: number; season: number | string; name: string; next_event: number; next_deadline: string; bank: number; free_transfers: number;
	overall_points?: number | null; overall_rank?: number | null; chips: Chip[];
	made: { out_name: string; in_name: string }[];
	squad: { fpl: number; api: number | null; name: string; pos: string; team?: number | null; fpl_team?: number; price: number; sell: number; status?: string | null; chance?: number | null }[];
};
export type LockMove = { out: number; in: number; out_name?: string; in_name?: string; sell?: number; buy?: number };
export type Lock = { season?: number | string; event_id: number; transfers: LockMove[]; locked_at: string };
export type OwnerAnswer =
	| { ok: true; docs?: { fpl_predictions?: PredDoc | null; fpl_team?: TeamDoc | null; efl_predictions?: PredDoc | null }; locks?: Lock[]; marks?: [number, boolean, boolean][] }
	| { ok: false; error?: string };

// ---- one player, and one of his matches
export type Cell = {
	gw: number; opponent: number; home: boolean; xp: number; minutes: number; goals: number; assists: number; parts: number[];
	p_clean_sheet?: number; np_goals?: number; pen_goals?: number; pen_misses?: number; fpl_pen_assists?: number; fpl_other_assists?: number;
	[k: string]: unknown;
};
export type FantasyPlayer = {
	player: number; name: string; team: number; position: string; pos: string; fpl_position?: string | null; price?: number | null;
	fpl_status?: string | null; fpl_chance?: number | null; availability?: string | null; corrected?: boolean; league?: number; cells: Cell[];
};
const named = <T>(fields: string[], r: unknown[]) => Object.fromEntries(fields.map((k, j) => [k, r[j]])) as T;

export function predRows(d: PredDoc): FantasyPlayer[] {
	return d.players.map((r, i) => {
		const p = named<FantasyPlayer>(d.fields, r);
		p.name = decodeEntities(String(p.name ?? ''));
		p.pos = p.fpl_position || p.position;
		p.league = d.teams[p.team]?.[2];
		p.cells = (d.cells[i] || []).map((c) => named<Cell>(d.cell_fields, c));
		return p;
	});
}
export const teamOf = (d: PredDoc, id: number | string) => d.teams[id]?.[0] || `Club ${id}`;
export const codeOf = (d: PredDoc, id: number | string) => d.teams[id]?.[1] || teamOf(d, id).slice(0, 3).toUpperCase();
// Home games in capitals, away in lower case
export const oppCode = (d: PredDoc, c: { opponent: number; home: boolean }) => (c.home ? codeOf(d, c.opponent) : codeOf(d, c.opponent).toLowerCase());
export const versus = (d: PredDoc, cells: { opponent: number; home: boolean }[]) =>
	cells.length ? cells.map((c) => `v ${teamOf(d, c.opponent)} ${c.home ? 'H' : 'A'}`).join(' · ') : 'No match (blank)';

// ---- the price slider: every £0.5m from the cheapest player to the dearest
export function priceStops(rows: FantasyPlayer[]): number[] {
	const prices = rows.map((p) => p.price).filter((v): v is number => v != null);
	if (!prices.length) return [];
	const lo = Math.floor(Math.min(...prices) / 5), hi = Math.ceil(Math.max(...prices) / 5);
	return Array.from({ length: hi - lo + 1 }, (_, i) => (lo + i) / 2);
}
export function priceLabel(stops: number[], a: number, b: number): string {
	const n = stops.length - 1, m = (v: number) => `£${v.toFixed(1)}m`;
	return a === 0 && b === n ? 'Any price' : a === 0 ? `Up to ${m(stops[b])}` : b === n ? `${m(stops[a])} and over` : `${m(stops[a])} to ${m(stops[b])}`;
}

// ---- the list
export type ListRow = { p: FantasyPlayer; cells: Cell[]; xp: number; minutes: number; goals: number; assists: number; price: number; value: number };
export type SortKey = 'xp' | 'minutes' | 'goals' | 'assists' | 'value';
export type FplView = {
	pos: string; q: string; sort: SortKey; mode: string; gw: number;
	price: [number | null, number | null]; mine: boolean; target: boolean;
};
export type Marks = { get(id: number): [boolean, boolean] | undefined };
// the gameweeks a view covers: one (mode "gw"), or the next 2, 5 or 10. A player's matches name
// their gameweek by its place in the list.
export const fplSpan = (d: PredDoc, v: FplView) =>
	v.mode === 'gw' ? [v.gw] : d.gameweeks.slice(0, Math.min(+v.mode, d.gameweeks.length)).map((_, i) => i);
const summed = (p: FantasyPlayer, cells: Cell[]): ListRow => {
	const sum = (k: 'xp' | 'minutes' | 'goals' | 'assists') => cells.reduce((a, c) => a + c[k], 0);
	const xp = sum('xp'), price = p.price == null ? null : p.price / 10;
	return { p, cells, xp, minutes: sum('minutes'), goals: sum('goals'), assists: sum('assists'), price: price ?? -1, value: price ? xp / price : -1 };
};
export function fplList(d: PredDoc, rows: FantasyPlayer[], v: FplView, marks: Marks): ListRow[] {
	const span = fplSpan(d, v), q = v.q.trim().toLowerCase(), [lo, hi] = v.price;
	return rows.map((p) => summed(p, p.cells.filter((c) => span.includes(c.gw))))
		.filter((r) => (v.pos === 'all' || r.p.pos === v.pos)
			&& ((lo == null && hi == null) || (r.price > 0 && (lo == null || r.price >= lo) && (hi == null || r.price <= hi)))
			// both boxes on: either
			&& ((!v.mine && !v.target) || (v.mine && !!marks.get(r.p.player)?.[0]) || (v.target && !!marks.get(r.p.player)?.[1]))
			&& (!q || r.p.name.toLowerCase().includes(q) || teamOf(d, r.p.team).toLowerCase().includes(q)))
		.sort((a, b) => b[v.sort] - a[v.sort] || b.xp - a.xp);
}
// A doubt over him: FPL's status first, the club's injury list otherwise
export function statusTag(p: { fpl_status?: string | null; fpl_chance?: number | null; availability?: string | null }): { text: string; title: string } | null {
	if (p.fpl_status && p.fpl_status !== 'a')
		return { text: p.fpl_status === 'd' ? `${Math.round(Number(p.fpl_chance ?? 50)) || 0}%` : FPL_STATUS[p.fpl_status] || 'Doubtful', title: 'FPL status' };
	if (p.availability) return { text: p.availability === 'Missing Fixture' ? 'Out' : 'Doubtful', title: 'On the injury list' };
	return null;
}
// Where a row's points come from, summed over the matches shown: one line a part with its main
// figure (minutes, clean sheet chance, expected goals or assists) and its points
export type PartLine = { label: string; figure: string; value: number };
export function partLines(d: PredDoc, r: ListRow, labels: Record<string, string>, splitPens = true): PartLine[] {
	const one = r.cells.length === 1 ? r.cells[0] : null;
	const sum = (k: string) => r.cells.reduce((a, c) => a + (Number(c[k]) || 0), 0);
	// v1.5 splits goals into open play and penalties (scored · missed), and adds the assists only FPL gives
	const pens = splitPens && r.cells[0] ? 'pen_goals' in r.cells[0] : false;
	const stat: Record<string, string> = {
		appearance: String(r.minutes), goal: (pens ? sum('np_goals') : r.goals).toFixed(2), assist: r.assists.toFixed(2),
		penalty: pens ? `${sum('pen_goals').toFixed(2)} · ${sum('pen_misses').toFixed(2)} missed` : '',
		fpl_assist: pens ? (sum('fpl_pen_assists') + sum('fpl_other_assists')).toFixed(2) : '',
		clean_sheet: one ? `${Math.round((one.p_clean_sheet ?? 0) * 100)}%` : ''
	};
	const names = pens ? { ...labels, goal: 'Goals (open play)' } : labels;
	return (d.part_fields || []).map((k, j) => ({ label: names[k] || k, figure: stat[k] ?? '', value: r.cells.reduce((a, c) => a + (c.parts?.[j] || 0), 0) }))
		.filter((x) => Math.abs(x.value) >= 0.005);
}
export const signed = (v: number, places = 2) => `${v < 0 ? '−' : ''}${Math.abs(v).toFixed(places)}`;

// ---- EFL Fantasy
export type ClubCell = { gw: number; opponent: number; home: boolean; xp: number; p_win: number; p_clean_sheet: number; parts: number[] };
export type ClubRow = { team: number; league?: number; cells: ClubCell[] };
export const eflClubRows = (d: PredDoc): ClubRow[] =>
	Object.entries(d.clubs || {}).map(([team, cs]) => ({ team: +team, league: d.teams[team]?.[2], cells: cs.map((c) => named<ClubCell>(d.club_fields || [], c)) }));
// The page opens on the next gameweek to start: one already under way (a match has kicked off, at
// the export or since) is a step back on the pager
export const eflNext = (gws: Gameweek[], now: number) => Math.max(0, gws.findIndex((g) => !g.started && Date.parse(g.first_kickoff) > now));
// The best 7 + 2 for one gameweek: for each formation, players by expected points with at most two
// from a club; the captain's points count twice. Greedy, so close to the best rather than exact.
export type BestTeam = { xi: { p: FantasyPlayer; xp: number }[]; total: number; formation: string; clubs: { c: ClubRow; xp: number }[] };
export function eflBestTeam(rows: FantasyPlayer[], clubs: ClubRow[], gw: number): BestTeam | null {
	const pts = (cells: { gw: number; xp: number }[]) => cells.filter((c) => c.gw === gw).reduce((a, c) => a + c.xp, 0);
	const pool = rows.map((p) => ({ p, xp: pts(p.cells) })).filter((r) => r.xp > 0).sort((a, b) => b.xp - a.xp);
	let best: BestTeam | null = null;
	for (const [nd, nm, nf] of EFL_FORMATIONS) {
		const need: Record<string, number> = { G: 1, D: nd, M: nm, F: nf }, per: Record<number, number> = {}, xi: BestTeam['xi'] = [];
		for (const r of pool) {
			if (!need[r.p.position] || (per[r.p.team] || 0) >= 2) continue;
			need[r.p.position]--; per[r.p.team] = (per[r.p.team] || 0) + 1; xi.push(r);
			if (xi.length === 7) break;
		}
		if (xi.length < 7) continue;
		const total = xi.reduce((a, r) => a + r.xp, 0) + xi[0].xp;
		if (!best || total > best.total) best = { xi, total, formation: `1-${nd}-${nm}-${nf}`, clubs: [] };
	}
	if (best) best.clubs = clubs.map((c) => ({ c, xp: pts(c.cells) })).filter((r) => r.xp > 0).sort((a, b) => b.xp - a.xp).slice(0, 2);
	return best;
}
export type EflView = { pos: string; league: string; q: string; sort: SortKey; mode: string; gw: number };
// the gameweeks a view covers, by their numbers (an EFL match names its gameweek by number)
export function eflSpan(d: PredDoc, v: EflView, next: number): number[] {
	const gws = d.gameweeks;
	return v.mode === 'gw' ? [gws[v.gw].id] : gws.slice(next, next + Math.min(+v.mode, gws.length - next)).map((g) => g.id);
}
const inLeague = (v: EflView, lg: number | undefined) => v.league === 'all' || String(lg) === v.league;
export function eflList(d: PredDoc, rows: FantasyPlayer[], v: EflView, span: number[]): ListRow[] {
	const q = v.q.trim().toLowerCase();
	return rows.filter((p) => inLeague(v, p.league) && (v.pos === 'all' || p.position === v.pos)
			&& (!q || p.name.toLowerCase().includes(q) || teamOf(d, p.team).toLowerCase().includes(q)))
		.map((p) => summed(p, p.cells.filter((c) => span.includes(c.gw))))
		.sort((a, b) => b[v.sort] - a[v.sort] || b.xp - a.xp);
}
export function eflClubList(d: PredDoc, clubs: ClubRow[], v: EflView, span: number[]): { c: ClubRow; cells: ClubCell[]; xp: number }[] {
	const q = v.q.trim().toLowerCase();
	return clubs.filter((c) => inLeague(v, c.league) && (!q || teamOf(d, c.team).toLowerCase().includes(q)))
		.map((c) => { const cells = c.cells.filter((x) => span.includes(x.gw)); return { c, cells, xp: cells.reduce((a, x) => a + x.xp, 0) }; })
		.filter((r) => r.cells.length).sort((a, b) => b.xp - a.xp);
}
export const eflSuggested = (rows: FantasyPlayer[], clubs: ClubRow[], v: EflView, gw: number) =>
	eflBestTeam(rows.filter((p) => inLeague(v, p.league)), clubs.filter((c) => inLeague(v, c.league)), gw);
