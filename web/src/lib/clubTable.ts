// The Clubs table's choices: the competition menu, the Exclude chips, the search and the rows
// they leave. Pure functions over the "site" and "rankings" rows, so they can be tested.
import {
	CLUB_ALIASES, CONTINENTS, COUNTRY_ALIASES, COUNTRY_FIRST, DOMESTIC_CUPS, EURO_CUPS, FLAG_CODES,
	LEAGUE_ALIASES, PRIMARY_COMPS, REGIONS, SHORT_NAMES, TABLE_COMPS, continentOf, regionLabel, regionOf
} from './names.ts';
import type { Club, Sort } from './rankings.ts';
import { leagueName, teamName, type Site } from './site.ts';

export type Country = { name: string; leagues: number[]; region: string | null };
// cup id -> the clubs a filter on that cup shows
export type Cups = Map<number, Set<number>>;

export const countryDisplay = (c: string) => (c === 'World' ? 'International' : (c || '').replace(/-/g, ' '));

// The countries with a tracked league that has ranked clubs: the big five first, then by name.
export function tableCountries(site: Site, all: Club[]): Country[] {
	const present = new Set(all.map((r) => String(r.league)));
	const byCountry = new Map<string, number[]>();
	for (const [id, c] of Object.entries(site.competitions)) {
		if (c.type !== 'League' || c.country === 'World' || !present.has(id)) continue;
		const name = c.country.replace(/-/g, ' ');
		if (!byCountry.has(name)) byCountry.set(name, []);
		byCountry.get(name)!.push(Number(id));
	}
	const rank = (n: string) => { const i = COUNTRY_FIRST.indexOf(n); return i === -1 ? 99 : i; };
	return [...byCountry.entries()]
		.map(([name, ids]) => ({ name, leagues: ids.sort((a, b) => a - b), region: COUNTRY_FIRST.includes(name) ? null : regionOf(name) }))
		.sort((a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name));
}

// ---- The menu's choice, as it is written in the address: "all", a league's id ("39"),
// "c:England", "r:Scandinavia", "e:all" / "e:2" (European cups), "k:all" / "k:45" (domestic cups)
export const isCupFilter = (f: string) => f.startsWith('e:') || f.startsWith('k:');
export function knownFilter(f: string | null, site: Site, countries: Country[]): f is string {
	if (!f) return false;
	if (f === 'all') return true;
	if (/^\d+$/.test(f)) return countries.some((c) => c.leagues.includes(Number(f)));
	const rest = f.slice(2);
	if (f.startsWith('c:')) return countries.some((c) => c.name === rest);
	if (f.startsWith('r:')) return REGIONS.includes(rest);
	const group = f.startsWith('e:') ? EURO_CUPS : f.startsWith('k:') ? DOMESTIC_CUPS : null;
	return !!group && (rest === 'all' || (/^\d+$/.test(rest) && group.includes(Number(rest))));
}
// League ids for a choice: null = all (a cup filter picks clubs, not leagues)
export function filterLeagues(f: string, countries: Country[]): number[] | null {
	if (f === 'all' || isCupFilter(f)) return null;
	if (f.startsWith('c:')) return countries.find((c) => c.name === f.slice(2))?.leagues || [];
	if (f.startsWith('r:')) return countries.filter((c) => c.region === f.slice(2)).flatMap((c) => c.leagues);
	return [Number(f)];
}
// the clubs for a cup filter ("e:all" / "k:all" = every cup in the group)
export function cupTeams(f: string, cups: Cups): Set<number> {
	const group = f === 'e:all' ? EURO_CUPS : f === 'k:all' ? DOMESTIC_CUPS : null;
	if (group) return new Set(group.flatMap((lid) => [...(cups.get(lid) || [])]));
	return cups.get(Number(f.slice(2))) || new Set();
}

// ---- Exclude: the big five countries and whole continents hidden from the table, on top of the
// menu, so "All" less the big five, or the Champions League less England. A search ignores it, as
// it does the menu. Keys: a big-five country's name, or "r:" + a continent (Europe takes in the
// big five too).
export const isExcludeKey = (k: string) => COUNTRY_FIRST.includes(k) || (k.startsWith('r:') && CONTINENTS.includes(k.slice(2)));
export function isExcluded(site: Site, ex: Set<string>, lid: number): boolean {
	if (!ex.size) return false;
	const c = site.competitions[lid]?.country?.replace(/-/g, ' ');
	if (!c || c === 'World') return false;
	return ex.has(c) || ex.has(`r:${continentOf(c)}`);
}

// ---- Search: every word typed must start a word of the club's text (its name, initials and
// nicknames, its league and country and theirs)
export const foldText = (t: string | undefined) =>
	String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const initials = (words: string[]) => (words.length >= 2 ? words.map((w) => w[0]).join('') : '');
const foldedAliases = new Map(Object.entries(CLUB_ALIASES).map(([n, a]) => [foldText(n), a]));
export function clubSearchText(site: Site, r: Club): string {
	const name = foldText(teamName(site, r.team));
	const parts = [name, initials(name.split(' ')), foldedAliases.get(name) || ''];
	if (/\bunited\b/.test(name)) parts.push('utd');
	if (/\butd\b/.test(name)) parts.push('united');
	const c = r.in_league ? site.competitions[r.league] : null;
	if (c) {
		const league = foldText(c.name), country = countryDisplay(c.country);
		const label = [...PRIMARY_COMPS, ...TABLE_COMPS].find((x) => x.id === String(r.league))?.label;
		parts.push(league, initials(league.split(' ')), foldText(SHORT_NAMES[r.league]), foldText(label),
			LEAGUE_ALIASES[r.league] || '', foldText(country), COUNTRY_ALIASES[c.country] || '',
			(FLAG_CODES[country] || '').replace('gb-', ''));
	}
	return ' ' + parts.filter(Boolean).join(' ') + ' ';
}

export type Choices = { filter: string; excluded: Set<string>; search: string; sort: Sort };

// The table's rows, highest first on the chosen column, and whether they span several leagues
// (then each row names its league, and the list sits in a box that scrolls).
export function tableRows(site: Site, all: Club[], countries: Country[], cups: Cups, ch: Choices): { rows: Club[]; wide: boolean } {
	const ids = filterLeagues(ch.filter, countries);
	const words = foldText(ch.search).split(' ').filter(Boolean);
	let rows: Club[];
	if (words.length) {
		rows = all.filter((r) => { const text = clubSearchText(site, r); return words.every((w) => text.includes(' ' + w)); });
	} else {
		if (isCupFilter(ch.filter)) {
			const teams = cupTeams(ch.filter, cups);
			rows = all.filter((r) => teams.has(r.team));
		} else {
			// clubs playing in a tracked league this season (drops clubs relegated out of every
			// tracked league and cup-only sides)
			const active = all.filter((r) => r.in_league);
			rows = ids === null ? active : active.filter((r) => ids.includes(r.league));
		}
		rows = rows.filter((r) => !isExcluded(site, ch.excluded, r.league));
	}
	rows = rows.slice().sort((a, b) => (b[ch.sort] ?? -1e9) - (a[ch.sort] ?? -1e9));
	return { rows, wide: ids === null || ids.length > 1 };
}

// ---- The menu as the page draws it: All, the cups, the big five countries, then the rest by
// region. A group opens on the choice inside it.
export type Chip = { value: string; label: string; full: string; title: string; count: number; pressed: boolean; group: boolean; hasActive: boolean };
export type MenuNode = { sep: true } | { sep?: false; chip: Chip; region?: boolean; open?: boolean; children?: MenuNode[] };
export type Menu = { nodes: MenuNode[]; name: string; count: number };

export function filterMenu(site: Site, all: Club[], countries: Country[], cups: Cups, f: string, ex: Set<string>): Menu {
	const counts = new Map<number, number>();
	let total = 0;
	for (const r of all) if (r.in_league && !isExcluded(site, ex, r.league)) { counts.set(r.league, (counts.get(r.league) || 0) + 1); total++; }
	const sum = (ids: number[]) => ids.reduce((n, id) => n + (counts.get(id) || 0), 0);
	const countOf = (value: string) => {
		if (value === 'all') return total;
		if (isCupFilter(value)) { const teams = cupTeams(value, cups); return all.filter((r) => teams.has(r.team) && !isExcluded(site, ex, r.league)).length; }
		return sum(filterLeagues(value, countries) || []);
	};
	const names = new Map<string, string>();
	const chip = (value: string, label: string, title: string, o: { group?: boolean; hasActive?: boolean; full?: string } = {}): Chip => {
		names.set(value, o.full ?? label);
		return { value, label, full: o.full ?? label, title, count: countOf(value), pressed: f === value, group: !!o.group, hasActive: !!o.hasActive };
	};
	const activeCountry = f.startsWith('c:') ? countries.find((c) => c.name === f.slice(2)) : countries.find((c) => c.leagues.includes(Number(f)));
	const activeRegion = f.startsWith('r:') ? f.slice(2) : activeCountry?.region;

	// A country: one league = a plain chip; several = a chip that opens its leagues
	const countryNode = (c: Country): MenuNode => {
		if (c.leagues.length === 1) return { chip: chip(String(c.leagues[0]), c.name, `${c.name} · ${leagueName(site, c.leagues[0])}`) };
		return {
			chip: chip(`c:${c.name}`, c.name, `All ${c.name} clubs`, { group: true, hasActive: c.leagues.includes(Number(f)) }),
			open: activeCountry === c,
			children: c.leagues.map((id) => ({ chip: chip(String(id), leagueName(site, id), leagueName(site, id), { full: `${c.name} · ${leagueName(site, id)}` }) }))
		};
	};
	const cupNode = (key: 'e' | 'k', label: string, title: string, ids: number[], each: (name: string) => string): MenuNode => ({
		chip: chip(`${key}:all`, label, title, { group: true, hasActive: f.startsWith(`${key}:`) && f !== `${key}:all` }),
		open: f.startsWith(`${key}:`),
		children: ids.map((lid) => ({ chip: chip(`${key}:${lid}`, leagueName(site, lid), each(leagueName(site, lid))) }))
	});
	const regions: MenuNode[] = REGIONS.flatMap((region) => {
		const members = countries.filter((c) => c.region === region);
		if (!members.length) return [];
		return [{
			chip: chip(`r:${region}`, regionLabel(region), `All clubs in ${region}`, { group: true, hasActive: activeRegion === region && f !== `r:${region}` }),
			region: true, open: activeRegion === region, children: members.map(countryNode)
		}];
	});
	const nodes: MenuNode[] = [
		{ chip: chip('all', 'All', 'All leagues') },
		cupNode('e', 'European cups', "Clubs in this season's Champions League, Europa League or Conference League", EURO_CUPS, (n) => `Clubs in the ${n} league phase`),
		cupNode('k', 'Domestic cups', "Clubs still in a domestic cup (clubs yet to enter aren't counted)", DOMESTIC_CUPS, (n) => `Clubs still in the ${n} (clubs yet to enter aren't counted)`),
		{ sep: true },
		...countries.filter((c) => !c.region).map(countryNode),
		{ sep: true },
		...regions
	];
	return { nodes, name: names.get(f) ?? 'All', count: countOf(f) };
}
