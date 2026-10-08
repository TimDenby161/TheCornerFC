import { playerBase } from '#lib/server/player.ts';
import { seasonShort } from '#lib/club.ts';
import { statText, sumSeason } from '#lib/player.ts';
import { compLabel } from '#lib/site.ts';

// One season (all his clubs added up), as totals or per 90 minutes: appearances, minutes, goals,
// assists and cards only (the feed's other counts aren't published)
export async function load({ fetch, params, url }) {
	const { site, lines, club } = await playerBase(fetch, params.id);
	if (!lines.length) return { any: false as const };
	const years = [...new Set(lines.map((r) => r.season))].sort((a, b) => b - a);
	const asked = Number(url.searchParams.get('s'));
	const year = years.includes(asked) ? asked : years[0];
	const rows = lines.filter((r) => r.season === year);
	const s = sumSeason(rows)!;
	const per90 = url.searchParams.get('per90') === '1' && !!s.minutes;
	const partial = rows.some((r) => r.starts == null);
	return {
		any: true as const, year, latest: years[0], per90, partial,
		years: years.map((y) => ({ y, label: seasonShort(y) })),
		clubs: rows.map((r) => ({ team: r.team, name: club(r.team), comp: compLabel(site, r.league), apps: r.apps, minutes: r.minutes })),
		apps: s.apps, started: s.starts != null && !partial ? s.starts : null, minutes: s.minutes ?? 0,
		goals: statText(s, 'goals', per90), assists: statText(s, 'assists', per90), yellow: statText(s, 'yellow', per90), red: statText(s, 'red', per90)
	};
}
