import { clubBase } from '#lib/server/club.ts';
import { clubHistory } from '#lib/club.ts';
import { leagueShort } from '#lib/site.ts';

// Season by season from the club's matches since 2020
export async function load({ fetch, params }) {
	const { site, rows, doc } = await clubBase(fetch, params.id);
	const seasons = clubHistory(rows, doc?.start ?? null, (lg) => site.competitions[lg]?.type === 'Cup');
	const lo = Math.min(...seasons.map((s) => s.end)) - 20, hi = Math.max(...seasons.map((s) => s.end));
	return {
		seasons: seasons.map((s) => ({
			...s, leagueName: s.league != null ? leagueShort(site, s.league) : null,
			// its bar in the chart: the lowest season's end sits a little above the floor
			bar: Math.max(6, (100 * (s.end - lo)) / (hi - lo || 1))
		}))
	};
}
