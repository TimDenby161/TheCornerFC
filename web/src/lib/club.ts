// A club's page, worked out from its own file (clubs/<id>): every match since 2020 with the
// rating after it, the manager, and the names of the clubs it has played.
export type ClubDoc = {
	id: number;
	start: number | null;
	fields: string[];
	matches: (string | number | number[] | null)[][];
	coach: { id?: number; name?: string; since?: string } | null;
	colors: string[] | null;
	teams: Record<string, string>;
};
export type ClubMatch = {
	date: string; rank: number; opponent: number;
	home: number; // 1 at home, 0 away, 2 on neutral ground
	gf: number; ga: number; league: number; formation: string | null;
	attack: number | null; defence: number | null; xi_lines: (number | null)[] | null;
	xgf: number | null; xga: number | null; xg_est: number | null;
};

export const clubMatches = (doc: ClubDoc | null): ClubMatch[] =>
	(doc?.matches || []).map((row) => Object.fromEntries(doc!.fields.map((f, i) => [f, row[i]])) as unknown as ClubMatch);

export const result = (m: { gf: number; ga: number }) => (m.gf > m.ga ? 'W' : m.gf === m.ga ? 'D' : 'L');
// W-D-L of a list of matches
export const wdl = (list: { gf: number; ga: number }[]) => {
	const w = list.filter((m) => m.gf > m.ga).length, d = list.filter((m) => m.gf === m.ga).length;
	return `${w}W ${d}D ${list.length - w - d}L`;
};
// a result's rating change: the rating after less the one before (the club file's start for the first)
export function clubMove(rows: ClubMatch[], i: number, start: number | null): number | null {
	const before = i > 0 ? rows[i - 1].rank : start;
	return before != null ? rows[i].rank - before : null;
}

// ---- Dates. A match day ("2026-09-19") is the same day for every visitor, so the server can
// write it; a kick-off time depends on where the visitor is (LocalTime.svelte).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const shortDate = (day: string) => `${Number(day.slice(8, 10))} ${MONTHS[Number(day.slice(5, 7)) - 1]}`;
export const longDate = (day: string) => `${shortDate(day)} ${day.slice(0, 4)}`;
export const seasonShort = (y: number) => `${String(y).slice(2)}/${String(y + 1).slice(2)}`;

// A club's seasons: July to June, or the calendar year for clubs that play through the summer
// (more matches in June/July than in December/January: MLS, Norway ...)
export function clubSeasons(rows: ClubMatch[]) {
	const month = (m: ClubMatch) => Number(m.date.slice(5, 7));
	const summer = rows.filter((m) => month(m) === 6 || month(m) === 7).length;
	const winter = rows.filter((m) => month(m) === 12 || month(m) === 1).length;
	const calendar = summer > winter;
	const seasonOf = (m: ClubMatch) => { const y = Number(m.date.slice(0, 4)); return calendar ? y : month(m) >= 7 ? y : y - 1; };
	return { calendar, seasonOf, label: (y: number) => (calendar ? String(y) : seasonShort(y)) };
}

// ---- History: season by season, newest first. `league`: the league most of its non-cup matches
// were in (isCup says which competitions are cups).
export type Season = {
	y: number; label: string; played: number; w: number; d: number; l: number; gf: number; ga: number;
	start: number | null; end: number; peak: number; league: number | null;
};
export function clubHistory(rows: ClubMatch[], start: number | null, isCup: (league: number) => boolean): Season[] {
	const { seasonOf, label } = clubSeasons(rows);
	const bySeason = new Map<number, { start: number | null; list: ClubMatch[] }>();
	rows.forEach((m, i) => {
		const y = seasonOf(m);
		if (!bySeason.has(y)) bySeason.set(y, { start: i > 0 ? rows[i - 1].rank : start, list: [] });
		bySeason.get(y)!.list.push(m);
	});
	return [...bySeason].reverse().map(([y, { start, list }]) => {
		const w = list.filter((m) => m.gf > m.ga).length, d = list.filter((m) => m.gf === m.ga).length;
		const leagueCount = new Map<number, number>();
		for (const m of list) if (!isCup(m.league)) leagueCount.set(m.league, (leagueCount.get(m.league) || 0) + 1);
		return {
			y, label: label(y), played: list.length, w, d, l: list.length - w - d,
			gf: list.reduce((a, m) => a + m.gf, 0), ga: list.reduce((a, m) => a + m.ga, 0),
			start, end: list[list.length - 1].rank, peak: Math.max(...list.map((m) => m.rank)),
			league: [...leagueCount].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
		};
	});
}

// ---- Formations: one entry per formation in a list of matches that have one (oldest first):
// most used first, with its share, record and goals, and when it was last used
export type FormationUse = { formation: string; matches: number; share: number; record: string; gf: number; ga: number; last: string };
export function formationUse(known: ClubMatch[]): FormationUse[] {
	const by = new Map<string, ClubMatch[]>();
	for (const m of known) { if (!by.has(m.formation!)) by.set(m.formation!, []); by.get(m.formation!)!.push(m); }
	return [...by]
		.sort((a, b) => b[1].length - a[1].length || b[1][b[1].length - 1].date.localeCompare(a[1][a[1].length - 1].date))
		.map(([formation, ms]) => ({
			formation, matches: ms.length, share: (100 * ms.length) / known.length, record: wdl(ms),
			gf: ms.reduce((a, m) => a + m.gf, 0), ga: ms.reduce((a, m) => a + m.ga, 0), last: ms[ms.length - 1].date
		}));
}
// A formation ("4-2-3-1") as dots on a 60 x 80 pitch: keeper at the top, attacking down
export function formationDots(f: string): [number, number][] {
	const lines = f.split('-').map(Number).filter((n) => n > 0);
	if (!lines.length) return [];
	const W = 60, y0 = 25, y1 = 70;
	const dots: [number, number][] = [[W / 2, 9]];
	lines.forEach((n, k) => {
		const y = lines.length === 1 ? (y0 + y1) / 2 : y0 + (k * (y1 - y0)) / (lines.length - 1);
		for (let i = 0; i < n; i++) dots.push([(W * (i + 1)) / (n + 1), y]);
	});
	return dots;
}

// ---- A league table's zones (promotion, Europe, relegation ...), from the notes on its rows:
// each note's class, in the order the notes first appear
export function leagueZones(rows: { description: string | null }[]): Map<string, string> {
	const zones = new Map<string, string>();
	let next = 0, releg = 0;
	for (const r of rows) {
		if (!r.description || zones.has(r.description)) continue;
		zones.set(r.description, /relegation/i.test(r.description) ? (releg++ ? 'zone-down2' : 'zone-down') : `zone-${Math.min(next++, 4)}`);
	}
	return zones;
}

// a 0 to 100 player rank's colour band
export const rankTier = (r: number) => (r >= 80 ? 4 : r >= 60 ? 3 : r >= 35 ? 2 : 1);
// a share of 100 as a class from placed.css
export const pct = (v: number) => Math.round(Math.max(0, Math.min(100, v)));

// Surname for tight spaces, keeping lower-case particles ("M. de Ligt" -> "de Ligt"), or the
// name a player is known by where that isn't his surname
const KNOWN_AS: Record<string, string> = { 'Gabriel Magalhães': 'Gabriel' };
export function shortName(name: string) {
	if (KNOWN_AS[name]) return KNOWN_AS[name];
	const parts = name.split(' ');
	let i = parts.length - 1;
	while (i > 1 && /^(de|da|do|dos|das|di|del|della|van|von|der|den|ten|ter|la|le|el|al|bin|ben)$/i.test(parts[i - 1])) i--;
	if (i === 1 && /^[a-z]/.test(parts[0])) i = 0;
	return parts.slice(i).join(' ');
}
// his first and last initials: "E. Haaland" -> "EH", "Rodri" -> "R"
export function personInitials(name: string) {
	const w = String(name || '').replace(/\./g, ' ').split(/\s+/).filter(Boolean);
	return w.length ? ([...w[0]][0] + (w.length > 1 ? [...w[w.length - 1]][0] : '')).toUpperCase() : '?';
}
