import { SHORT_NAMES } from './names.ts';

// The "site" row: names for every competition and club, and when each source was last fetched.
export type Competition = { name: string; country: string; type: string };
export type Site = {
	generated_at: string;
	competitions: Record<string, Competition>;
	teams: Record<string, string>;
};

export const teamName = (site: Site, id: number) => site.teams[id] || `Team ${id}`;
export const leagueShort = (site: Site, id: number) =>
	SHORT_NAMES[id] || site.competitions[id]?.name || '';
export const countryName = (c: Competition) => c.country.replace(/-/g, ' ');
export const leagueName = (site: Site, id: number) => SHORT_NAMES[id] || site.competitions[id]?.name || `Competition ${id}`;

export const ordinal = (n: number) => {
	const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
	return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

// No club badges: a chip instead, the club's initials on a colour worked out from its id.
const CREST_SKIP = new Set(['fc', 'afc', 'cf', 'sc', 'ac', 'as', 'cd', 'ud', 'sd', 'rc', 'fk', 'sk',
	'nk', 'bk', 'sv', 'if', 'de', 'del', 'la', 'le', 'el', 'the', 'and', 'of', '&']);
export function crestInitials(name: string, skip: boolean) {
	const all = String(name || '').replace(/[.'’]/g, '').split(/[\s-]+/).filter(Boolean);
	const kept = skip ? all.filter((w) => !CREST_SKIP.has(w.toLowerCase())) : all;
	const words = kept.length ? kept : all;
	if (!words.length) return '?';
	return (words.length === 1
		? [...words[0]].slice(0, 3).join('')
		: words.slice(0, 3).map((w) => [...w][0]).join('')
	).toUpperCase();
}
export const crestHue = (id: number) => Math.round(((Number(id) || 0) * 137.508) % 360) % 360;
