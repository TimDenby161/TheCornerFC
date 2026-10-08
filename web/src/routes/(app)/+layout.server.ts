import { keptDoc } from '#lib/server/database.ts';
import type { Site } from '#lib/site.ts';

// At the foot of every page of the site: when each source of its data was last fetched
type Fresh = Site & { freshness?: { predictions?: string; injuries?: string; odds?: string; model?: { name: string; code?: string; registered?: string } } };
export async function load({ fetch }) {
	const site = await keptDoc<Fresh>(fetch, 'site').catch(() => null);
	const f = site?.freshness || {};
	return {
		fresh: {
			items: ([
				['Data updated', site?.generated_at, "When this site's data was last exported"],
				['Predictions updated', f.predictions, 'Latest match prediction written'],
				['Injuries updated', f.injuries, 'Latest injury and suspension list fetched'],
				['Odds last seen', f.odds, 'Latest bookmaker prices fetched']
			] as [string, string | undefined, string][]).filter((x): x is [string, string, string] => !!x[1]),
			model: f.model ?? null
		}
	};
}
