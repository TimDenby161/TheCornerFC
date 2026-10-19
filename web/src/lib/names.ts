// Names, short forms and groupings the pages share. Carried over from the old site's app.js. The
// tables are in names.json, which the C# site (site/) reads too.
import names from './names.json';

export const SHORT_NAMES: Record<number, string> = names.SHORT_NAMES;
export const CLUB_SHORT: Record<number, string> = names.CLUB_SHORT;
// (no prototype, so a country called "constructor" finds no flag)
export const FLAG_CODES: Record<string, string> = Object.assign(Object.create(null), names.FLAG_CODES);
export const COUNTRY_FIRST: string[] = names.COUNTRY_FIRST;
export const REGIONS: string[] = names.REGIONS;
export const EURO_CUPS: number[] = names.EURO_CUPS;
export const DOMESTIC_CUPS: number[] = names.DOMESTIC_CUPS;
export const CONTINENTS: string[] = names.CONTINENTS;
export const CLUB_ALIASES: Record<string, string> = names.CLUB_ALIASES;
export const LEAGUE_ALIASES: Record<number, string> = names.LEAGUE_ALIASES;
export const COUNTRY_ALIASES: Record<string, string> = names.COUNTRY_ALIASES;
export const PRIMARY_COMPS: { id: string; label: string; ids?: number[] }[] = names.PRIMARY_COMPS;
export const TABLE_COMPS: { id: string; label: string }[] = names.TABLE_COMPS;
// the order competitions are listed in where several are shown together
export const GROUP_ORDER: number[] = names.GROUP_ORDER;

// Every country outside the big five goes under a region; anything not listed is "Rest of Europe"
// (UEFA members such as Turkey, Israel and Kazakhstan included).
const REGION_OF: Record<string, string> = {};
for (const [region, list] of Object.entries(names.REGION_LISTS as Record<string, string[]>)) for (const c of list) REGION_OF[c] = region;
export const regionOf = (country: string) => REGION_OF[country] || 'Rest of Europe';
// chip labels: "N. America", "S. America" (the full name stays in the key, links and hover text)
export const regionLabel = (r: string) => r.replace(/^(North|South) America$/, (m, d) => `${d[0]}. America`);
export const continentOf = (country: string) => {
	const region = COUNTRY_FIRST.includes(country) ? 'Europe' : regionOf(country);
	return CONTINENTS.includes(region) ? region : 'Europe'; // the European regions
};
