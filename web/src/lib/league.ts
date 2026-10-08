// A competition's page, worked out from its own file (leagues/<id>, or the whole of it through
// site_league for a subscriber): the table, the season's fixtures with the model's predictions,
// and each club's recent expected goals.
import { FINISHED, type Match } from './matches.ts';
import type { Club } from './rankings.ts';
import type { Site } from './site.ts';

export type LeagueFile = {
	id: number; season: number; start: string | null;
	table_fields: string[]; table: (string | number | null)[][];
	fixture_fields: string[]; fixtures: (string | number | null)[][];
	recent_xg_fields?: string[]; recent_xg?: Record<string, number[]>;
	teams: Record<string, string>;
	// cut: the database left the season's projections out for this visitor (the paywall); what it
	// gives instead is `projected`, each club's projected place and points
	cut?: boolean; projected_fields?: string[]; projected?: (string | number | null)[][];
};
export type TableRow = {
	group: string | null; rank: number; team: number; played: number | null; win: number | null; draw: number | null; lose: number | null;
	gf: number | null; ga: number | null; gd: number | null; points: number | null; form: string | null; description: string | null;
	// estimated xG and xG conceded per 90 over its last five league games with shot counts
	xg90: number | null; xga90: number | null; xg_games: number;
};
export type Fixture = {
	id: number; kickoff: string; round: string | null; home: number; away: number; status: string;
	hg: number | null; ag: number | null; pen_h: number | null; pen_a: number | null;
	home_xg: number | null; away_xg: number | null; p_home: number | null; p_draw: number | null; p_away: number | null;
};
const named = <T>(fields: string[], rows: unknown[][]) => rows.map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])) as T);

export function tableRows(lg: LeagueFile): TableRow[] {
	const xf = lg.recent_xg_fields || [];
	return named<TableRow>(lg.table_fields, lg.table).map((r) => {
		const x = lg.recent_xg?.[r.team];
		return { ...r, xg90: x ? x[xf.indexOf('xg90')] : null, xga90: x ? x[xf.indexOf('xga90')] : null, xg_games: x ? x[xf.indexOf('games')] : 0 };
	});
}
export const fixtureRows = (lg: LeagueFile) => named<Fixture>(lg.fixture_fields, lg.fixtures);
export const headline = (lg: LeagueFile) => named<{ group: string | null; place: number; team: number; left: number; points: number }>(lg.projected_fields || [], lg.projected || []);
// "2026/27" for a season that starts in the second half of the year, "2026" for a calendar-year one
export function seasonLabel(lg: LeagueFile): string {
	const month = Number(String(lg.start || lg.fixtures[0]?.[1] || '').slice(5, 7));
	return month >= 6 ? `${lg.season}/${String(lg.season + 1).slice(2)}` : String(lg.season);
}
export const roundLabel = (r: string | null) => (r || '').replace(/^Regular Season - (\d+)$/, 'Round $1');

// ---- Clubs and averages
// clubs playing their league football in this competition this season, best rated first
export const leagueClubs = (all: Club[], lid: number) => all.filter((r) => r.in_league && r.league === lid).sort((a, b) => b.lt - a.lt);
export const avgRating = (rows: Club[]) => (rows.length ? rows.reduce((a, r) => a + r.lt, 0) / rows.length : null);
// The clubs in a competition that have a rating: this season's league members plus anyone in its
// table (or, with no table yet, its fixtures), strongest first by Baseline Strength
export function leagueRanked(all: Club[], lid: number, table: TableRow[], fixtures: Fixture[]): Club[] {
	const ids = new Set([...table.map((r) => r.team), ...leagueClubs(all, lid).map((r) => r.team)]);
	if (!table.length) for (const f of fixtures) { ids.add(f.home); ids.add(f.away); }
	const byTeam = new Map(all.map((c) => [c.team, c]));
	return [...ids].map((t) => byTeam.get(t)).filter((c): c is Club => !!c).sort((a, b) => b.lt - a.lt);
}
// Every league with rated clubs this season, with the averages of their ratings
export function leagueAverages(site: Site, all: Club[]) {
	const avgOf = (rows: Club[], k: 'lt' | 'current') => rows.reduce((t, r) => t + r[k], 0) / rows.length;
	return Object.entries(site.competitions).filter(([, c]) => c.type === 'League').flatMap(([lid, c]) => {
		const clubs = leagueClubs(all, Number(lid));
		if (!clubs.length) return [];
		const lt = avgOf(clubs, 'lt'), current = avgOf(clubs, 'current');
		return [{ lid: Number(lid), name: c.name, country: c.country, clubs: clubs.length, lt, current, trend: Math.round(current) - Math.round(lt) }];
	});
}

// ---- Sortable tables: a column's first click sorts it best first (dir 1 = ascending), a second
// reverses. Blanks last; ties keep the table's own order.
export type Cols<T> = Record<string, { dir: 1 | -1; val: (r: T) => string | number | null | undefined }>;
export type Sort = { key: string; dir: 1 | -1 };
export function pickSort<T>(cols: Cols<T>, def: string, key: string | null, reversed: boolean): Sort {
	const k = key && cols[key] ? key : def;
	return { key: k, dir: (reversed ? -cols[k].dir : cols[k].dir) as 1 | -1 };
}
export function sortRows<T>(rows: T[], s: Sort, cols: Cols<T>): T[] {
	const val = cols[s.key].val;
	return rows.map((r, i) => [r, i] as const).sort(([a, i], [b, j]) => {
		const x = val(a), y = val(b);
		if (x == null || y == null) return x == null && y == null ? i - j : x == null ? 1 : -1;
		return (typeof x === 'string' ? x.localeCompare(y as string) : x - (y as number)) * s.dir || i - j;
	}).map(([r]) => r);
}
const FORM_PTS: Record<string, number> = { W: 3, D: 1, L: 0 };
export const formPoints = (form: string | null) => (form ? [...form].reduce((a, c) => a + (FORM_PTS[c] ?? 0), 0) : null);

// ---- Projected table: the rest of the season played out SIMS times from the model's predictions.
// Each upcoming match's score is drawn from its Poisson grid, scaled to its home / draw / away
// chances. Each simulated season also gives every club a random true strength (STRENGTH_SD, on the
// log of its expected goals), shared by all its matches: the model's ratings are estimates, and a
// club that is really a little better or worse is so every week. Without it the matches are
// independent coin flips, their luck evens out over a season and the leaders' chances come out
// far too high.
export const SIMS = 5000;
const STRENGTH_SD = 0.15;
const SHIFT_STEP = 0.05, SHIFT_MAX = 16; // strength gaps rounded to 0.05, capped at ±0.8
type Sim = Fixture & { home_xg: number; away_xg: number; p_home: number; p_draw: number; p_away: number; fix?: number[] };
const pmf = (lam: number) => { const out = [], m = Math.max(lam, 0.01); let p = Math.exp(-m); for (let k = 0; k <= 10; k++) { out.push(p); p *= m / (k + 1); } return out; };
// one match's scores at a strength gap of `shift` (home minus away), most likely first, as
// cumulative chances. The model's result chances are kept by reweighting each result by the same
// factor that matches the unshifted grid to them.
function scoreTable(f: Sim, shift = 0) {
	if (!f.fix) {
		const ph = pmf(f.home_xg), pa = pmf(f.away_xg), sums = [0, 0, 0]; // home win, draw, away win
		for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) sums[i > j ? 0 : i === j ? 1 : 2] += ph[i] * pa[j];
		f.fix = [f.p_home, f.p_draw, f.p_away].map((w, k) => (sums[k] ? w / sums[k] : 0));
	}
	const e = Math.exp(shift), ph = pmf(f.home_xg * e), pa = pmf(f.away_xg / e);
	const cells = [];
	for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) cells.push({ i, j, p: ph[i] * pa[j] * f.fix[i > j ? 0 : i === j ? 1 : 2] });
	cells.sort((x, y) => y.p - x.p);
	const cdf = new Float64Array(cells.length), hg = new Int8Array(cells.length), ag = new Int8Array(cells.length);
	let acc = 0;
	cells.forEach((c, n) => { cdf[n] = acc += c.p; hg[n] = c.i; ag[n] = c.j; });
	return { cdf, hg, ag, total: acc };
}
// the fixtures the model has projected: the ones a season can be played out from
export const projectable = (fixtures: Fixture[]) => fixtures.filter((f): f is Sim => f.p_home != null && f.home_xg != null && f.away_xg != null && f.p_draw != null && f.p_away != null);
export type Projected = { team: number; left: number; w: number; d: number; l: number; pts: number; gd: number; pos: number[] };
// (`random`: the source of chance, so a test can fix it)
export function projectGroup(rows: TableRow[], fixtures: Sim[], sims = SIMS, random: () => number = Math.random): Projected[] {
	const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
	const n = rows.length, idx = new Map(rows.map((r, i) => [r.team, i]));
	const games = fixtures.filter((f) => idx.has(f.home) || idx.has(f.away)).map((f) => {
		const tables: ReturnType<typeof scoreTable>[] = new Array(2 * SHIFT_MAX + 1);
		tables[SHIFT_MAX] = scoreTable(f);
		return { h: idx.has(f.home) ? idx.get(f.home)! : -1, a: idx.has(f.away) ? idx.get(f.away)! : -1, f, tables, hs: 0, as: 0 };
	});
	// clubs outside this group (other groups' opponents) get their own strength draw too
	const outside = new Map<number, number>(); let m = n;
	for (const f of fixtures) for (const t of [f.home, f.away]) if (!idx.has(t) && !outside.has(t)) outside.set(t, m++);
	for (const g of games) { g.hs = g.h >= 0 ? g.h : outside.get(g.f.home)!; g.as = g.a >= 0 ? g.a : outside.get(g.f.away)!; }
	const pos = rows.map(() => new Float64Array(n)), sumPts = new Float64Array(n), sumGd = new Float64Array(n);
	const pts = new Float64Array(n), gd = new Float64Array(n), gf = new Float64Array(n), tie = new Float64Array(n);
	const strength = new Float64Array(m);
	const order = rows.map((_, i) => i);
	for (let s = 0; s < sims; s++) {
		for (let i = 0; i < n; i++) { const r = rows[i]; pts[i] = r.points || 0; gd[i] = r.gd || 0; gf[i] = r.gf || 0; tie[i] = random(); }
		for (let i = 0; i < m; i++) strength[i] = STRENGTH_SD * gauss();
		for (const g of games) {
			const k = Math.max(-SHIFT_MAX, Math.min(SHIFT_MAX, Math.round((strength[g.hs] - strength[g.as]) / SHIFT_STEP)));
			const t = g.tables[k + SHIFT_MAX] || (g.tables[k + SHIFT_MAX] = scoreTable(g.f, k * SHIFT_STEP));
			const u = random() * t.total, cdf = t.cdf;
			let c = 0;
			while (c < cdf.length - 1 && cdf[c] < u) c++;
			const hg = t.hg[c], ag = t.ag[c], hp = hg > ag ? 3 : hg === ag ? 1 : 0, ap = hg < ag ? 3 : hg === ag ? 1 : 0;
			if (g.h >= 0) { pts[g.h] += hp; gd[g.h] += hg - ag; gf[g.h] += hg; }
			if (g.a >= 0) { pts[g.a] += ap; gd[g.a] += ag - hg; gf[g.a] += ag; }
		}
		order.sort((x, y) => pts[y] - pts[x] || gd[y] - gd[x] || gf[y] - gf[x] || tie[y] - tie[x]);
		for (let p = 0; p < n; p++) pos[order[p]][p]++;
		for (let i = 0; i < n; i++) { sumPts[i] += pts[i]; sumGd[i] += gd[i]; }
	}
	const left = rows.map(() => 0), xw = rows.map(() => 0), xd = rows.map(() => 0);
	for (const { h, a, f } of games) {
		if (h >= 0) { left[h]++; xw[h] += f.p_home; xd[h] += f.p_draw; }
		if (a >= 0) { left[a]++; xw[a] += f.p_away; xd[a] += f.p_draw; }
	}
	return rows.map((r, i) => ({ team: r.team, left: left[i], w: (r.win || 0) + xw[i], d: (r.draw || 0) + xd[i],
		l: (r.lose || 0) + left[i] - xw[i] - xd[i], pts: sumPts[i] / sims, gd: sumGd[i] / sims, pos: [...pos[i]].map((c) => c / sims) }))
		.sort((x, y) => y.pts - x.pts || y.gd - x.gd);
}
// a chance as the projected table shows it
export const chanceText = (p: number) => (p <= 0 ? '–' : p < 0.005 ? '<1%' : p > 0.995 && p < 1 ? '>99%' : `${Math.round(p * 100)}%`);

// ---- A league's own matches tab: its rounds in the order they are first played, and the one to
// open on (the round with the next fixture, else the last)
const OFF = new Set(['CANC', 'PST', 'ABD']);
export function leagueRounds(fixtures: Fixture[]): { rounds: string[]; open: string | null } {
	const rounds = [...new Set(fixtures.map((f) => f.round || ''))];
	const next = fixtures.find((f) => !FINISHED.has(f.status) && !OFF.has(f.status));
	return { rounds, open: next ? next.round || '' : rounds[rounds.length - 1] ?? null };
}
export const offText = (status: string) => (status === 'PST' ? 'Postponed' : status === 'CANC' ? 'Cancelled' : status === 'ABD' ? 'Abandoned' : null);
export type { Match };
