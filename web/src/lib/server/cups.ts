import { cupEntrants, cupTeamsLeft, type LeagueDoc } from '#lib/cups.ts';
import type { Cups } from '#lib/clubTable.ts';
import { DOMESTIC_CUPS, EURO_CUPS } from '#lib/names.ts';
import { keptDoc } from './database.ts';

// Which clubs each cup filter shows, from the cups' own files (kept five minutes). A cup whose
// file can't be read shows no clubs.
export async function loadCups(fetch: typeof globalThis.fetch): Promise<Cups> {
	const ids = [...EURO_CUPS, ...DOMESTIC_CUPS];
	const docs = await Promise.all(ids.map((id) => keptDoc<LeagueDoc>(fetch, `leagues/${id}`, 300_000).catch(() => null)));
	return new Map(ids.map((id, i) => {
		const lg = docs[i];
		return [id, !lg ? new Set<number>() : DOMESTIC_CUPS.includes(id) ? cupTeamsLeft(lg) : cupEntrants(lg)];
	}));
}
