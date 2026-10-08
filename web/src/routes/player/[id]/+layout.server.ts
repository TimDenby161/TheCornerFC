import { playerBase } from '#lib/server/player.ts';
import { longDate, seasonShort, shortDate } from '#lib/club.ts';
import { countryDisplay } from '#lib/clubTable.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { leagueShort } from '#lib/site.ts';

const RECENT_DAYS = 45; // latest appearance older than this: not shown as recent form

export async function load({ fetch, params, setHeaders }) {
	const { id, site, p, doc, apps, now, year, club } = await playerBase(fetch, params.id);
	setHeaders({ 'cache-control': 'public, max-age=60' });
	const league = p.team && p.league ? leagueShort(site, p.league) : '';
	const last = apps[0];
	const days = last ? Math.floor((Date.now() - new Date(last.date).getTime()) / 864e5) : null;

	return {
		id, name: p.name, locked: p.locked,
		team: p.team ? { id: p.team, name: club(p.team) } : null,
		league: league && p.league != null ? { id: p.league, name: league } : null,
		nat: p.nationality ? { name: p.nationality, flag: FLAG_CODES[p.nationality] ?? FLAG_CODES[countryDisplay(p.nationality)] ?? null } : null,
		position: p.position || '', age: p.age, born: doc?.born ? longDate(doc.born) : null,
		rank: p.rank == null ? null : Math.round(p.rank),
		season: seasonShort(year), seasonName: `${year}/${String(year + 1).slice(2)}`,
		now,
		// his place by Ability among his league's players, counted by the export
		leagueRank: p.lg_n && p.lg_rank != null ? { place: p.lg_rank, of: p.lg_n } : null,
		// Recent Performance: his latest league appearances, dated so old ones aren't read as form
		recent: {
			stale: days == null || days > RECENT_DAYS, days, lastDate: last ? longDate(last.date) : null,
			apps: apps.slice(0, 10).map((m) => ({
				gf: m.gf, ga: m.ga, goals: m.goals, assists: m.assists,
				title: `${shortDate(m.date)} ${m.home ? 'v' : '@'} ${club(m.opponent)} ${m.gf}–${m.ga} · ${m.minutes}′${m.goals ? ` · ${m.goals} G` : ''}${m.assists ? ` · ${m.assists} A` : ''}`
			}))
		}
	};
}
