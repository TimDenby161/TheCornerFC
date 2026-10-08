// National teams. The ranking ("nations": the club Elo run over every men's international since
// 1872) and a nation's own file (nations/<team id>: its matches, line-ups and stat lines from
// API-Football). Nothing here is a model: the "predicted XI" is read off the current coach's
// recent team sheets.
import { decodeEntities } from './players.ts';

export type NationsDoc = {
	latest_match: string; matches: number; from_api?: number; aliases?: Record<string, string[]>;
	nations: { name: string; flag: string; confed: string | null; current: number; year_ago: number | null; played: number; w: number; d: number; l: number;
		last: { date: string; opp: string; gf: number; ga: number; comp: string }; team_id?: number | null }[];
};
export const CONFEDS = ['UEFA', 'CONMEBOL', 'CONCACAF', 'CAF', 'AFC', 'OFC'];
// A nationality page's nation in the ranking (API-Football's name or the dataset's)
export const nationFor = (d: NationsDoc, nat: string) => d.nations.find((x) => x.name === nat || (d.aliases?.[x.name] || []).includes(nat));
// A rating's place among the nations, as the badge colours: top 5% green, 20% amber, half orange
export function nationTier(d: NationsDoc, v: number) {
	const share = (d.nations.filter((n) => n.current > v).length + 1) / d.nations.length;
	return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
}

export type NationDoc = {
	id: number; name: string; coach: { id?: number; name?: string; since?: string } | null;
	match_fields: string[]; matches: (string | number | null)[][];
	app_fields: string[]; apps: (string | number | null)[][];
	players: Record<string, string>;
};
export type App = { match: number; player: number; minutes: number | null; started: number; role: string | null; goals: number | null; assists: number | null; yellow: number | null; red: number | null };
export type NatMatch = { i: number; date: string; opp: string; venue: string; gf: number; ga: number; tournament: string | null; formation: string | null; coach: string | null; coach_id: number | null; xi: App[] };
export type Team = { matches: NatMatch[]; apps: App[]; players: Record<string, string>; coach: { id?: number; name?: string; since?: string } | null };

// A nation's file made ready: names as text (API-Football sends some HTML-encoded), each match
// with the eleven that started it
export function readTeam(doc: NationDoc): Team {
	const named = <T>(fields: string[], rows: unknown[][]) => rows.map((r) => Object.fromEntries(fields.map((f, i) => [f, r[i]])) as T);
	const text = (t: string | null) => (t == null ? t : decodeEntities(t));
	const matches = named<Omit<NatMatch, 'i' | 'xi'>>(doc.match_fields, doc.matches)
		.map((m, i) => ({ ...m, opp: text(m.opp)!, coach: text(m.coach), tournament: text(m.tournament), i, xi: [] as App[] }));
	const apps = named<App>(doc.app_fields, doc.apps);
	for (const a of apps) if (a.started) matches[a.match]?.xi.push(a);
	return {
		matches, apps, coach: doc.coach?.name ? { ...doc.coach, name: decodeEntities(doc.coach.name) } : doc.coach,
		players: Object.fromEntries(Object.entries(doc.players).map(([id, name]) => [id, decodeEntities(name)]))
	};
}

// The current coach's matches (oldest first). With his start date (when he's the coach on the
// latest team sheet): the matches since then. Else his unbroken spell up to the latest match on
// the team sheets, from his first known one. Every match when the latest names no coach.
// full: the stored matches go back to the start of his spell
export type Spell = { coach: string | null; coachId?: number | null; since?: string; rows: NatMatch[]; full: boolean };
export function nationSpell(team: Team): Spell {
	const rows = team.matches, head = team.coach;
	const last = rows[rows.length - 1];
	if (head?.since && head.name && (last.coach_id == null || last.coach_id === head.id)) {
		const list = rows.filter((m) => m.date >= head.since!);
		if (list.length) return { coach: head.name, coachId: head.id, since: head.since, rows: list, full: rows[0].date <= head.since };
	}
	const coach = last.coach;
	if (!coach) return { coach: null, rows, full: false };
	let k = rows.length;
	while (k > 0 && (rows[k - 1].coach === coach || rows[k - 1].coach == null)) k--;
	while (rows[k].coach == null) k++;
	return { coach, coachId: last.coach_id, rows: rows.slice(k), full: k > 0 };
}
export const spellLabel = ({ coach }: Spell) => (coach ? `Under ${coach}` : 'All matches (coach not known)');

export const ROLE_ORDER = ['GK', 'RB', 'RWB', 'CB', 'LB', 'LWB', 'DM', 'RM', 'CM', 'LM', 'AM', 'RW', 'ST', 'LW'];
// Each role's cell on the overview pitch [row, column] (column 1 is the right: attacking down the page)
export const ROLE_CELL: Record<string, [number, number]> = { GK: [1, 2], RB: [2, 1], CB: [2, 2], LB: [2, 3], RWB: [3, 1], DM: [3, 2], LWB: [3, 3],
	RM: [4, 1], CM: [4, 2], LM: [4, 3], RW: [5, 1], AM: [5, 2], LW: [5, 3], ST: [6, 2] };
// A player's main position -> the roles he fits, nearest first (the first the shape has is his)
export const POS_FIT: Record<string, string[]> = { GK: ['GK'], CB: ['CB', 'DM'], RB: ['RB', 'RWB', 'RM', 'CB'], LB: ['LB', 'LWB', 'LM', 'CB'],
	RWB: ['RWB', 'RB', 'RM', 'RW'], LWB: ['LWB', 'LB', 'LM', 'LW'], DM: ['DM', 'CM', 'CB'], CM: ['CM', 'DM', 'AM'],
	AM: ['AM', 'CM', 'ST', 'RW', 'LW'], RM: ['RM', 'RW', 'RWB', 'AM', 'CM'], LM: ['LM', 'LW', 'LWB', 'AM', 'CM'],
	RW: ['RW', 'RM', 'AM', 'ST'], LW: ['LW', 'LM', 'AM', 'ST'], ST: ['ST', 'AM'] };

const NAT_XI_RECENT = 6;   // his latest team sheets weighed
const NAT_XI_DECAY = 0.75; // each older sheet counts this much of the one after it
const ROLE_NEAR: Record<string, string[]> = { GK: [], CB: [], RB: ['RWB'], LB: ['LWB'], RWB: ['RB', 'RM'], LWB: ['LB', 'LM'], DM: ['CM'],
	CM: ['DM', 'AM'], AM: ['CM', 'ST'], RM: ['RW', 'RWB'], LM: ['LW', 'LWB'], RW: ['RM', 'ST'], LW: ['LM', 'ST'], ST: ['AM'] };
// The team's usual shape: its most used formation in the current coach's last 5 team sheets (ties:
// the latest), as {role: count} from his latest XI in it. Null without full team sheets
export function nationShape(team: Team) {
	const spell = nationSpell(team);
	const sheets = spell.rows.filter((m) => m.xi.length >= 11 && m.xi.every((a) => a.role)).slice(-NAT_XI_RECENT);
	if (!sheets.length) return null;
	const counts = new Map<string, number>();
	for (const m of sheets.slice(-5)) if (m.formation) counts.set(m.formation, (counts.get(m.formation) || 0) + 1);
	const latest = [...sheets].reverse();
	const formation = [...counts].sort((a, b) => b[1] - a[1] || latest.findIndex((m) => m.formation === a[0]) - latest.findIndex((m) => m.formation === b[0]))[0]?.[0];
	const template = latest.find((m) => m.formation === formation) || latest[0];
	const need = new Map<string, number>();
	for (const a of template.xi) need.set(a.role!, (need.get(a.role!) || 0) + 1);
	return { spell, sheets, formation: template.formation, template, need };
}
// The predicted XI, from the current coach's recent team sheets (no model). His most used
// formation in his last 5 matches, laid out as his latest XI in it; then each of its positions
// goes to the player who has started there most, recent matches counting more (a start in a
// neighbouring position counts half). Players their club lists as out injured are left out.
export function nationPredictedXi(team: Team, injured: Set<number>) {
	const shape = nationShape(team);
	if (!shape) return null;
	const { sheets, template, need } = shape;
	const score = new Map<string, number>(), starts = new Map<number, number>();
	sheets.forEach((m, k) => {
		const w = NAT_XI_DECAY ** (sheets.length - 1 - k);
		for (const a of m.xi) {
			starts.set(a.player, (starts.get(a.player) || 0) + 1);
			for (const [role, f] of [[a.role!, 1], ...(ROLE_NEAR[a.role!] || []).map((r) => [r, 0.5])] as [string, number][])
				score.set(`${role}:${a.player}`, (score.get(`${role}:${a.player}`) || 0) + f * w);
		}
	});
	const picks: { role: string; pid: number; starts: number }[] = [], placed = new Set<number>(), filled = new Map<string, number>();
	[...score].map(([key, v]) => { const [role, pid] = key.split(':'); return { role, pid: Number(pid), v }; })
		.filter((c) => need.has(c.role) && !injured.has(c.pid))
		.sort((a, b) => b.v - a.v || (starts.get(b.pid) || 0) - (starts.get(a.pid) || 0))
		.forEach((c) => {
			if (placed.has(c.pid) || (filled.get(c.role) || 0) >= need.get(c.role)!) return;
			placed.add(c.pid);
			filled.set(c.role, (filled.get(c.role) || 0) + 1);
			picks.push({ role: c.role, pid: c.pid, starts: starts.get(c.pid) || 0 });
		});
	const order = (r: string) => ROLE_ORDER.indexOf(r) + 1 || 99;
	return {
		formation: template.formation, picks: picks.sort((a, b) => order(a.role) - order(b.role)),
		// regulars (2+ starts in these sheets) missing through injury
		out: [...starts].filter(([pid, n]) => n >= 2 && injured.has(pid)).map(([pid]) => pid)
	};
}

// ---- Overview: the best by current rank in each position of the team's usual shape (3 per
// player the shape has there: 6 for a pair of centre-backs), each player in the nearest of its
// positions to his main one, plus everyone the current coach has picked. Without line-ups, the
// top 3 in each of a fixed set of positions. `list`: the nationality's ranked players, in the
// export's order (by current rank; a hidden rank keeps its place).
export type Listed = { id: number; name: string; rank: number | null; ord: number | null; position: string | null; team: number | null };
const byOrd = (a: { ord?: number | null; name: string }, b: { ord?: number | null; name: string }) => (a.ord ?? 1e9) - (b.ord ?? 1e9) || a.name.localeCompare(b.name);
export function overviewPitch(list: Listed[], team: Team | null) {
	const shape = team?.matches.length ? nationShape(team) : null;
	const layout: [string, number, number, number][] = shape
		? [...shape.need].sort((a, b) => ROLE_ORDER.indexOf(a[0]) - ROLE_ORDER.indexOf(b[0])).map(([role, n]) => [role, 3 * n, ...ROLE_CELL[role]])
		: [['GK', 3, 1, 2], ['RB', 3, 2, 1], ['CB', 3, 2, 2], ['LB', 3, 2, 3], ['DM', 3, 3, 2], ['CM', 3, 4, 2], ['RW', 3, 5, 1], ['AM', 3, 5, 2], ['LW', 3, 5, 3], ['ST', 3, 6, 2]];
	const roles = new Set(layout.map((l) => l[0]));
	const slotOf = (pos: string | null) => (pos ? (POS_FIT[pos] || [pos]).find((r) => roles.has(r)) : undefined);
	// everyone the current coach has picked (played for him, starting or from the bench): our
	// ranked players by their main position, the rest by the one they've started in most for him
	type Shown = { id: number; name: string; rank: number | null; ord?: number | null; position: string | null; team?: number | null; listed: boolean };
	const picked = new Map<number, Shown>();
	if (shape && team) {
		const inSpell = new Set(shape.spell.rows.map((m) => m.i));
		const started = new Map<number, Map<string, number>>();
		const ids = new Set<number>();
		for (const a of team.apps) {
			if (!inSpell.has(a.match)) continue;
			ids.add(a.player);
			if (a.started && a.role) { const c = started.get(a.player) || new Map(); started.set(a.player, c.set(a.role, (c.get(a.role) || 0) + 1)); }
		}
		for (const pid of ids) {
			const p = list.find((q) => q.id === pid);
			const role = [...(started.get(pid) || [])].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
			picked.set(pid, p ? { ...p, listed: true } : { id: pid, name: team.players[pid] || 'Unknown', rank: null, position: role, listed: false });
		}
	}
	return {
		formation: shape?.formation ?? null, coach: shape?.spell.coach ?? null, hasShape: !!shape,
		boxes: layout.map(([label, max, row, col]) => {
			const top = list.filter((p) => slotOf(p.position) === label).slice(0, max);
			const topIds = new Set(top.map((p) => p.id));
			const extra = [...picked.values()].filter((p) => p.position && slotOf(p.position) === label && !topIds.has(p.id));
			// (a top player the coach hasn't picked is shown in red)
			const ps = [...top.map((p) => ({ p: { ...p, listed: true } as Shown, unpicked: !!shape && !picked.has(p.id) })), ...extra.map((p) => ({ p, unpicked: false }))]
				.sort((a, b) => byOrd(a.p, b.p));
			return { label, row, col, players: ps };
		})
	};
}

// ---- Players: everyone who has played under the current coach
export type NatPlayer = { id: number; name: string; apps: number; minutes: number; noMins: number; goals: number; assists: number; y: number; r: number; cards: number; last: string; role: string };
export const NAT_PLAYER_SORTS = ['apps', 'minutes', 'goals', 'assists', 'cards', 'last'] as const;
export function nationPlayers(team: Team, spell: Spell, clubPosition: (id: number) => string | null, sort: (typeof NAT_PLAYER_SORTS)[number]): NatPlayer[] {
	const inWindow = new Set(spell.rows.map((m) => m.i));
	const by = new Map<number, NatPlayer & { roles: Map<string, number> }>();
	for (const a of team.apps) {
		if (!inWindow.has(a.match)) continue;
		let p = by.get(a.player);
		if (!p) by.set(a.player, (p = { id: a.player, name: team.players[a.player] || 'Unknown', apps: 0, minutes: 0, noMins: 0, goals: 0, assists: 0, y: 0, r: 0, cards: 0, last: '', role: '', roles: new Map() }));
		const m = team.matches[a.match];
		p.apps++;
		if (a.minutes == null) p.noMins++; else p.minutes += a.minutes;
		p.goals += a.goals || 0; p.assists += a.assists || 0;
		p.y += a.yellow || 0; p.r += a.red || 0;
		if (m.date > p.last) p.last = m.date;
		if (a.role) p.roles.set(a.role, (p.roles.get(a.role) || 0) + 1);
	}
	const players = [...by.values()].map(({ roles, ...p }) => ({ ...p, cards: p.y + 3 * p.r, role: [...roles].sort((a, b) => b[1] - a[1])[0]?.[0] || clubPosition(p.id) || '' }));
	const val = (p: NatPlayer) => p[sort];
	return players.sort((a, b) => (val(b) > val(a) ? 1 : val(b) < val(a) ? -1 : 0) || b.apps - a.apps || b.minutes - a.minutes);
}
