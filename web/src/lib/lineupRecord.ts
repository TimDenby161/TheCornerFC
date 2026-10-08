// The line-up record: every XI the model predicted before the team sheet came out, checked
// against the one that started ("lineups": one row per team line-up, totalled here), or the
// reconstructed history: the model re-run on every past match, which is 63,000 line-ups and so
// is added up in the database (site_lineup_history). Both end up as the same summary, which is
// all the page draws from.
import { addDays, localDay } from './matchday.ts';

export const LR_LINES = ['Goalkeeper', 'Defence', 'Midfield', 'Attack'];
const LR_HORIZONS: [string, number, number][] = [['Under 1 hour', 0, 1], ['1–6 hours', 1, 6], ['6–24 hours', 6, 24], ['24 hours or more', 24, Infinity]];
export const LR_PAGE = 50;     // line-ups listed per "Show more"
export const LR_CLUB_MIN = 3;  // line-ups a club needs for the easiest/hardest lists

export type LiveDoc = {
	available?: boolean; fields: string[]; rows: unknown[][]; versions: { name?: string; registered?: string }[];
	teams?: Record<string, string>; players?: Record<string, string>; excluded_no_official_xi?: number;
};
export type LiveRow = { fixture: number; kickoff: string; league: number; team: number; opponent: number; home: number; correct: number; roles_right: number; roles_known: number;
	lines: number[]; hours_before: number; version: number; missed: number[]; wrong: number[]; time: number };
export type HistoryDoc = {
	available?: boolean; any: boolean; leagues: number[]; scope: Record<string, number>;
	total: number; correct: number; perfect: number; roles_right: number; roles_known: number; matches: number; first: string | null; last: string | null;
	counts: Record<string, number>; step: Step; trend: [string, number, number, number][]; lines: number[];
	comps: Group[]; clubs: Group[]; missed: [number, number, number][]; wrong: [number, number, number][]; missed_total: number;
	rows: [string, number, number, number, number, number, number[]][]; teams?: Record<string, string>; players?: Record<string, string>;
};
type Step = 'day' | 'week' | 'month';
// [key, line-ups, starters named, perfect XIs, right position, positions known]
export type Group = [number, number, number, number, number?, number?];
export type Summary = {
	any: boolean; n: number; correct: number; perfect: number; rolesRight: number; rolesKnown: number; matches: number; excluded?: number;
	first?: string; last?: string;                    // days ("2026-09-08")
	counts?: number[];                                // line-ups by starters named (0 to 11)
	step?: Step; trend?: [string, number, number, number][]; // [day the period starts, line-ups, named, perfect], newest first
	lines?: number[];                                 // [starters, of them named] for the four lines, flat
	timing?: [string, number, number, number][];      // the live record only: by how long before kick-off it was saved
	comps?: Group[]; clubs?: Group[];
	missed?: [number, number, number][]; wrong?: [number, number, number][]; missedTotal?: number; // [player, his club, times], twice or more
	versions?: Group[];                               // the live record only
	rows?: { day: string; team: number; opponent: number; home: boolean; league: number; correct: number; missed: number[] }[];
};

export const liveRows = (d: LiveDoc): LiveRow[] => d.rows.map((r) => {
	const o = Object.fromEntries(d.fields.map((k, i) => [k, r[i]])) as unknown as LiveRow;
	o.time = Date.parse(o.kickoff);
	return o;
});
function groups<T>(list: T[], key: (r: T) => number | string, of: (r: T) => { correct: number; roles_right: number; roles_known: number }): [number | string, number, number, number, number, number][] {
	const out = new Map<number | string, [number | string, number, number, number, number, number]>();
	for (const r of list) {
		const k = key(r), x = of(r);
		const g = out.get(k) || [k, 0, 0, 0, 0, 0];
		g[1] += 1; g[2] += x.correct; g[3] += x.correct === 11 ? 1 : 0; g[4] += x.roles_right; g[5] += x.roles_known;
		out.set(k, g);
	}
	return [...out.values()];
}
const self = (r: LiveRow) => r;

// The live record's summary for a range and some competitions. `tz`: the visitor's time zone, for
// which day a line-up falls on; `shown`: how many line-ups to list.
export function liveSummary(d: LiveDoc, all: LiveRow[], days: number | null, ids: number[] | null, tz: string, shown: number, now = Date.now()): Summary {
	const since = days ? now - days * 864e5 : -Infinity;
	const list = all.filter((r) => r.time >= since && (!ids || ids.includes(r.league)));
	const [[, n = 0, correct = 0, perfect = 0, rolesRight = 0, rolesKnown = 0] = []] = groups(list, () => 0, self);
	const s: Summary = { any: all.length > 0, n, correct, perfect, rolesRight, rolesKnown, matches: new Set(list.map((r) => r.fixture)).size, excluded: d.excluded_no_official_xi };
	if (!n) return s;
	s.first = localDay(list[0].time, tz); s.last = localDay(list[n - 1].time, tz);
	s.counts = Array(12).fill(0);
	for (const r of list) s.counts[r.correct] += 1;
	// average per day; per week past four weeks, per month past six months
	const span = list[n - 1].time - list[0].time;
	const step: Step = (s.step = span > 183 * 864e5 ? 'month' : span > 28 * 864e5 ? 'week' : 'day');
	s.trend = (groups(list, (r) => {
		const day = localDay(r.time, tz);
		if (step === 'week') return addDays(day, -((new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7));
		return step === 'month' ? `${day.slice(0, 7)}-01` : day;
	}, self) as [string, number, number, number, number, number][]).sort((a, b) => b[0].localeCompare(a[0])).map(([k, a, b, c]) => [k, a, b, c]);
	s.lines = Array.from({ length: 8 }, (_, i) => list.reduce((a, r) => a + r.lines[i], 0));
	s.timing = LR_HORIZONS.map(([label, a, b]) => {
		const [, x = 0, y = 0, z = 0] = groups(list.filter((r) => r.hours_before >= a && r.hours_before < b), () => 0, self)[0] || [];
		return [label, x, y, z];
	});
	s.comps = groups(list, (r) => r.league, self) as Group[];
	s.clubs = groups(list, (r) => r.team, self) as Group[];
	for (const field of ['missed', 'wrong'] as const) {
		const c = new Map<number, [number, number, number]>();
		for (const r of list) for (const p of r[field]) { const x = c.get(p) || [p, r.team, 0]; x[2] += 1; c.set(p, x); }
		s[field] = [...c.values()].filter((x) => x[2] >= 2);
	}
	s.missedTotal = list.reduce((a, r) => a + r.missed.length, 0);
	s.versions = (groups(list, (r) => r.version, self) as Group[]).sort((a, b) => a[0] - b[0]);
	s.rows = [...list].reverse().slice(0, shown).map((r) => ({ day: localDay(r.time, tz), team: r.team, opponent: r.opponent, home: !!r.home, league: r.league, correct: r.correct, missed: r.missed }));
	return s;
}
// The history's summary: the database's answer, in the same shape
export function historySummary(d: HistoryDoc): Summary {
	return {
		any: d.any, n: d.total, correct: d.correct, perfect: d.perfect, rolesRight: d.roles_right, rolesKnown: d.roles_known, matches: d.matches,
		first: d.first ?? undefined, last: d.last ?? undefined,
		counts: Array.from({ length: 12 }, (_, k) => d.counts[k] || 0), step: d.step, trend: d.trend,
		lines: d.lines, comps: d.comps, clubs: d.clubs, missed: d.missed, wrong: d.wrong, missedTotal: d.missed_total,
		rows: d.rows.map(([day, team, opponent, home, league, correct, missed]) => ({ day, team, opponent, home: !!home, league, correct, missed }))
	};
}
// the clubs easiest and hardest to predict, among those with enough line-ups scored
export function clubExtremes(clubs: Group[]): { easiest: Group[]; hardest: Group[] } | null {
	const ranked = clubs.filter((c) => c[1] >= LR_CLUB_MIN).sort((a, b) => b[2] / b[1] - a[2] / a[1] || b[1] - a[1]);
	const k = Math.min(10, Math.floor(ranked.length / 2));
	return k >= 3 ? { easiest: ranked.slice(0, k), hardest: ranked.slice(-k).reverse() } : null;
}
export const of11 = (x: number) => `${x.toFixed(1)} of 11`;
export const shareText = (a: number, b: number | undefined) => (b ? `${((100 * a) / b).toFixed(1)}%` : '–');
