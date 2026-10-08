// The Matches page: a day at a time on the visitor's own calendar, or, for one competition, a
// round at a time. The server works the days out in the visitor's time zone (it learns that from
// a cookie the page sets; UK time until then).
import { CALLED_OFF, FINISHED, NO_GAME, roundName, type Match } from './matches.ts';
import { COUNTRY_FIRST, DOMESTIC_CUPS, EURO_CUPS, REGIONS, regionOf } from './names.ts';
import type { Country } from './clubTable.ts';
import type { Site } from './site.ts';

// ---- Days in a time zone
export const validZone = (tz: string | undefined | null): tz is string => {
	if (!tz || tz.length > 64) return false;
	try { new Intl.DateTimeFormat('en-GB', { timeZone: tz }); return true; } catch { return false; }
};
// What the time zone cookie says of a visitor. It holds their browser's zone, so the server can
// write days and kick-off times in their own time; or TZ_OFF, where they have chosen UK time in
// the menu, and then their zone is never kept. No cookie yet: UK time until the page sets it.
export const TZ_OFF = 'off', UK_ZONE = 'Europe/London';
export const zoneChoice = (cookie: string | undefined | null): { tz: string; ukTime: boolean } =>
	cookie === TZ_OFF ? { tz: UK_ZONE, ukTime: true } : { tz: validZone(cookie) ? cookie : UK_ZONE, ukTime: false };
const dayFormat = new Map<string, Intl.DateTimeFormat>();
// the calendar day ("2026-10-10") an instant falls on there
export function localDay(at: string | number | Date, tz: string): string {
	let f = dayFormat.get(tz);
	if (!f) dayFormat.set(tz, (f = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' })));
	return f.format(new Date(at));
}
export const isDay = (d: string | null | undefined): d is string => !!d && /^\d{4}-\d\d-\d\d$/.test(d) && !Number.isNaN(Date.parse(`${d}T00:00:00Z`));
export const addDays = (day: string, n: number) => new Date(Date.parse(`${day}T00:00:00Z`) + n * 864e5).toISOString().slice(0, 10);
// the instant that day starts there (midnight on its clocks)
export function dayStart(day: string, tz: string): Date {
	const want = Date.parse(`${day}T00:00:00Z`);
	let at = want;
	// what the clocks there read at `at`, as if it were UTC: the gap is the zone's offset then
	const wall = (t: number) => {
		const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
			.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
		return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
	};
	for (let i = 0; i < 3; i++) at = want - (wall(at) - at); // again, in case the offset changes that night
	return new Date(at);
}
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// "Sat 10 Oct" for a calendar day
export const dayName = (day: string) => { const d = new Date(`${day}T00:00:00Z`); return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; };
const shortDay = (day: string) => { const d = new Date(`${day}T00:00:00Z`); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; };

// ---- Which days have matches: [day on the visitor's calendar, competition, matches]
export type MatchDays = { days: [string, number, number][]; leagues: number[]; intl: [number, number][] };
export const daysWith = (md: MatchDays, ids: number[] | null) => [...new Set(md.days.filter(([, lid]) => !ids || ids.includes(lid)).map(([day]) => day))].sort();
// Today if anything is on, otherwise the nearest upcoming day with matches
export function defaultDay(md: MatchDays, today: string): string {
	const days = daysWith(md, null);
	if (days.includes(today)) return today;
	return days.find((d) => d > today) || days[days.length - 1] || today;
}

// ---- The competition menu over the competitions with matches (cups under their country, the
// European cups and the national team competitions in groups of their own)
// Order competition groups are stacked in on the page (anything else follows)
export const GROUP_ORDER = [39, 40, 41, 42, 2, 3, 848, 45, 48, 46, 140, 135, 78, 61, 94, 88, 144, 179, 43, 50, 51, 47];
const orderOf = (id: number) => { const i = GROUP_ORDER.indexOf(id); return i === -1 ? 999 : i; };
export function compCountries(site: Site, ids: number[]): Country[] {
	const comps = site.competitions;
	const byCountry = new Map<string, number[]>();
	for (const id of new Set(ids.filter((id) => comps[id]))) {
		const c = comps[id];
		if (c.country === 'World') continue;
		const name = c.country.replace(/-/g, ' ');
		if (!byCountry.has(name)) byCountry.set(name, []);
		byCountry.get(name)!.push(id);
	}
	const rank = (n: string) => { const i = COUNTRY_FIRST.indexOf(n); return i === -1 ? 99 : i; };
	// leagues before cups, then the page's usual order
	const byOrder = (a: number, b: number) => Number(comps[a].type !== 'League') - Number(comps[b].type !== 'League') || orderOf(a) - orderOf(b) || a - b;
	return [...byCountry.entries()]
		.map(([name, list]) => ({ name, leagues: list.sort(byOrder), region: COUNTRY_FIRST.includes(name) ? null : regionOf(name) }))
		.sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
}
// a menu choice this page knows: a competition, country or region it has, or a cup group
export function knownMatchFilter(f: string | null, site: Site, countries: Country[]): f is string {
	if (!f) return false;
	if (f === 'all') return true;
	if (/^\d+$/.test(f)) return !!site.competitions[f];
	const rest = f.slice(2);
	if (f.startsWith('c:')) return countries.some((c) => c.name === rest);
	if (f.startsWith('r:')) return REGIONS.includes(rest);
	return (f.startsWith('e:') || f.startsWith('i:')) && (rest === 'all' || (/^\d+$/.test(rest) && !!site.competitions[rest]));
}
// Competition ids for a choice: null = all
export function filterComps(f: string, countries: Country[], intl: number[]): number[] | null {
	if (f === 'all') return null;
	if (f === 'e:all') return EURO_CUPS;
	if (f === 'k:all') return DOMESTIC_CUPS;
	if (f === 'i:all') return intl;
	if (f.startsWith('e:') || f.startsWith('k:') || f.startsWith('i:')) return [Number(f.slice(2))];
	if (f.startsWith('c:')) return countries.find((c) => c.name === f.slice(2))?.leagues || [];
	if (f.startsWith('r:')) return countries.filter((c) => c.region === f.slice(2)).flatMap((c) => c.leagues);
	return [Number(f)];
}
// The competition a choice picks on its own (a league, one European cup, one international
// competition), or null: such a page goes a round at a time
export const singleComp = (f: string) => (/^\d+$/.test(f) ? Number(f) : /^[ei]:\d+$/.test(f) ? Number(f.slice(2)) : null);

// ---- Rounds: a competition's rounds in date order. Group stages (cup rounds named after the
// group) go by week instead, one "Group stage" entry per week.
const ROUND_WINDOW = 4 * 864e5; // a match more than 4 days from its round's middle was rearranged
export type Round = { key: string; label: string; matches: Match[]; mid: number; first: number; last: number; pending: boolean };
export function matchRounds(matches: Match[], tz: string): Round[] {
	const byKey = new Map<string, { key: string; label: string; matches: Match[] }>();
	for (const m of matches) {
		if (m.status === 'PST') continue; // back under its new date once rescheduled
		let key = m.round || '', label = roundName(key);
		if (!key || /^Group /.test(key)) {
			const day = localDay(m.kickoff, tz), dow = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7;
			key = `w:${addDays(day, -dow)}`; // that week's Monday
			label = 'Group stage';
		}
		if (!byKey.has(key)) byKey.set(key, { key, label, matches: [] });
		byKey.get(key)!.matches.push(m);
	}
	return [...byKey.values()].map((r) => {
		r.matches.sort((a, b) => a.kickoff.localeCompare(b.kickoff));
		const times = r.matches.map((m) => Date.parse(m.kickoff));
		const mid = times[Math.floor(times.length / 2)];
		const own = times.filter((t) => Math.abs(t - mid) <= ROUND_WINDOW); // its scheduled dates
		return {
			...r, mid, first: Math.min(...own), last: Math.max(...own),
			// still to come: a match in its own window that hasn't been played (or called off)
			pending: r.matches.some((m) => !FINISHED.has(m.status) && !NO_GAME.has(m.status) && Math.abs(Date.parse(m.kickoff) - mid) <= ROUND_WINDOW)
		};
	}).sort((a, b) => a.mid - b.mid);
}
// The round to show: the one on a day asked for (or the next after it), else the one on now or
// next up (the first with matches still to play, else the last)
export function pickRound(rounds: Round[], day: string | null, tz: string): Round | null {
	if (!rounds.length) return null;
	const asked = day ? rounds.find((r) => localDay(r.last, tz) >= day) : null;
	return asked || rounds.find((r) => r.pending) || rounds[rounds.length - 1];
}
export function roundDates(r: Round, tz: string): string {
	const a = shortDay(localDay(r.first, tz)), b = shortDay(localDay(r.last, tz));
	return a === b ? a : `${a} – ${b}`;
}

// ---- A match card's figures
// Home, draw and away as whole percentages that add up to 100, as the bars show them
export const shownProbs = (home: number, draw: number): [number, number, number] => {
	const h = Math.round(home * 100), d = Math.round(draw * 100);
	return [h, d, 100 - h - d];
};
// Goals to one decimal, never "0.0" for something the model did count
export const goalsText = (v: number) => { const a = Math.abs(v); return a === 0 ? '0' : a < 0.05 ? '<0.1' : a.toFixed(1); };
export const signedGoals = (v: number) => (v !== 0 && Math.abs(v) < 0.05 ? '≈0' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${goalsText(v)}`);
// One key reason as a phrase and its size; + favours the home side (or, for tendencies, more goals)
export function reasonText(key: string, v: number, home: string, away: string): { text: string; size: string } | null {
	const fav = v >= 0 ? home : away, other = v >= 0 ? away : home;
	const text = ({
		strength: `${fav} rated the stronger side`,
		home_advantage: `Home advantage for ${fav}`,
		europe_home: `Extra home advantage in European ties for ${fav}`,
		home_edges: `Clubs' home/away records lean to ${fav}`,
		absences: `More of ${other}'s regulars listed as missing`,
		lineups: `Predicted line-up rated higher for ${fav}`,
		tendencies: v >= 0 ? "Both sides' games tend to be open" : "Both sides' games tend to be tight"
	} as Record<string, string>)[key];
	return text ? { text, size: key === 'tendencies' ? `${signedGoals(v)} total goals` : `${goalsText(v)} goals` } : null;
}
export { CALLED_OFF };
