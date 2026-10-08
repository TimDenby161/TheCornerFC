
import { countryDisplay } from '#lib/clubTable.ts';
import { leagueAverages } from '#lib/league.ts';
import { markPredicted, spots, type Starter, type XiRow } from '#lib/lineups.ts';
import { liveRows, type HistoryDoc, type LiveDoc } from '#lib/lineupRecord.ts';
import { dayName, localDay, shownProbs } from '#lib/matchday.ts';
import { FLAG_CODES } from '#lib/names.ts';
import { nationTier, type NationsDoc } from '#lib/nation.ts';
import { decodeEntities, playerRows, type PlayersAnswer } from '#lib/players.ts';
import { tiers, type Club } from '#lib/rankings.ts';
import { pctText, type StatsDoc } from '#lib/stats.ts';
import { compLabel, leagueShort, teamName, type Site } from '#lib/site.ts';
import { clubFixtures } from './club.ts';
import { keptAsk, keptDoc } from './database.ts';

// Home's slides: a sample of the real thing from each part of the site. Each is worked out from
// what its own page reads, as a visitor who isn't signed in sees it; one whose sample can't be had
// is left out (null).
const TOP = 7;        // rows in a slide's list
const quiet = <T>(p: Promise<T>): Promise<T | null> => p.catch(() => null);
type Fetch = typeof globalThis.fetch;

export const homeClubs = (site: Site, all: Club[]) => [...all].sort((a, b) => b.current - a.current).slice(0, TOP)
	.map((x) => ({ team: x.team, name: teamName(site, x.team), comp: compLabel(site, x.league), current: Math.round(x.current), form: x.form == null ? null : Math.round(x.form) }));

export function homeLeagues(site: Site, all: Club[]) {
	const tier = tiers(all, 'lt');
	return leagueAverages(site, all).sort((a, b) => b.lt - a.lt).slice(0, TOP)
		.map((c) => ({ lid: c.lid, name: c.name, sub: `${countryDisplay(c.country)} · ${c.clubs} clubs`, lt: Math.round(c.lt), tier: tier(c.lt) }));
}
// The first of the Players list, as it opens
export async function homePlayers(fetch: Fetch, site: Site) {
	const d = await quiet(keptAsk<PlayersAnswer>(fetch, 'site_players', { p_limit: TOP }));
	const rows = d ? playerRows(site, d.rows).filter((p) => p.seasons?.[0] != null) : [];
	return rows.length ? rows.map((p) => ({
		id: p.id, name: p.name, team: p.team, teamName: p.team ? teamName(site, p.team) : null, league: p.league != null ? leagueShort(site, p.league) : '',
		nat: p.nationality, flag: p.nationality ? FLAG_CODES[p.nationality] ?? null : null,
		pos: ({ G: 'GK', D: 'DEF', M: 'MID', F: 'FWD' } as Record<string, string>)[p.position || ''] || p.position || '', rank: p.seasons![0]!
	})) : null;
}
export async function homeNations(fetch: Fetch) {
	const d = await quiet(keptDoc<NationsDoc>(fetch, 'nations', 300_000));
	return d ? [...d.nations].sort((a, b) => b.current - a.current).slice(0, TOP).map((n) => ({
		name: n.name, flag: FLAG_CODES[n.name] ?? null, confed: n.confed || '', current: Math.round(n.current), tier: nationTier(d, n.current),
		change: n.year_ago == null ? null : Math.round(n.current - n.year_ago)
	})) : null;
}
// The last year of the Stats page, by its strongest true figures: how many matches were marked
// (the headline), how often a result the model gave 70% or more came in, the right-result rate
// against always picking the home team, the exact scores, the goals it was off by, how far the
// chances it gave were from how often they happened, and the competitions marked.
const SURE = 0.7;
export async function homeStats(fetch: Fetch) {
	const doc = await quiet(keptDoc<StatsDoc>(fetch, 'stats', 300_000));
	const s = doc?.ranges?.['365d']?.all;
	if (!s?.n) return null;
	const bands = (s.calibration || []).filter(([count]) => count) as [number, number, number][];
	const sure = bands.filter(([, said]) => said >= SURE);
	const calls = sure.reduce((t, b) => t + b[0], 0), came = sure.reduce((t, b) => t + b[0] * b[2], 0), said = bands.reduce((t, b) => t + b[0], 0);
	const comps = Object.keys(doc!.ranges['365d']).filter((k) => k !== 'all').length;
	return {
		matches: s.n.toLocaleString('en-GB'),
		nums: [
			calls ? [pctText(came / calls, 0), '', `of the results the model gave ${pctText(SURE, 0)} or more came in`] : null,
			[pctText(s.correct ?? 0, 0), '', `right result, against ${pctText(s.home_rate ?? 0, 0)} by picking the home team every time`],
			s.exact ? [`1 in ${Math.round(1 / s.exact)}`, '', 'exact scores right'] : null,
			s.goal_error != null ? [s.goal_error.toFixed(2), '', 'goals off per team, on average'] : null,
			said ? [((100 * bands.reduce((t, b) => t + b[0] * Math.abs(b[1] - b[2]), 0)) / said).toFixed(1), ' pts', 'between the chance it gave and how often it happened'] : null,
			comps ? [comps.toLocaleString('en-GB'), '', 'competitions marked'] : null
		].filter((x): x is string[] => !!x),
		note: s.live < s.n ? `${s.live.toLocaleString('en-GB')} recorded before kickoff, the rest reconstructed from pre-match data.` : ''
	};
}
// A few matches' chances as a taste of the Matches page: the next match of each of the strongest
// clubs that has the model's chances, soonest first (two of them meeting is one match)
const CALL_CLUBS = 4, CALLS = 3;
export async function homeCalls(fetch: Fetch, site: Site, all: Club[], tz: string) {
	const teams = [...all].sort((a, b) => b.current - a.current).slice(0, CALL_CLUBS).map((x) => x.team);
	const lists = await Promise.all(teams.map((t) => quiet(clubFixtures(fetch, site, t))));
	const now = Date.now();
	const next = lists.map((l) => (l?.matches || []).filter((x) => x.status === 'NS' && x.p_home != null && x.p_draw != null && Date.parse(x.kickoff) > now)[0]).filter(Boolean);
	const ms = [...new Map(next.map((m) => [m.id, m])).values()].slice(0, CALLS).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
	if (!ms.length) return null;
	return {
		day: localDay(ms[0].kickoff, tz),
		calls: ms.map((m) => {
			const [h, d, a] = shownProbs(m.p_home!, m.p_draw!);
			return { id: m.id, home: teamName(site, m.home), away: teamName(site, m.away), comp: compLabel(site, m.league), kickoff: m.kickoff, h, d, a };
		})
	};
}
// The example line-up: the XI that started, on a pitch, marked against the one the model
// predicted for it. Always a club in the world's top ten, so a name a visitor knows: its latest
// match where the model named nine or ten of the eleven, not all of them, so the slide shows a
// miss marked too. From the Line-up record where it has one (the last three weeks); where it
// doesn't, as while the record is new, from the reconstructed history's last 30 days, and the
// slide says so. No top-ten club with a nine or a ten there: the latest of theirs with all
// eleven, then their latest of any. None at all: left out.
const XI_CLUBS = 10, XI_RIGHT = 9, XI_DAYS = 30;
const fair = (right: number) => right >= XI_RIGHT && right < 11;
type Lineups = { actual: Record<string, XiRow[]> | null; prematch: Record<string, XiRow[]> | null } | null;
export async function homeXi(fetch: Fetch, site: Site, all: Club[], tz: string) {
	const top = [...all].sort((a, b) => b.current - a.current).slice(0, XI_CLUBS);
	const known = new Set(top.map((x) => x.team));
	const lineups = (fixture: number) => quiet(keptAsk<Lineups>(fetch, 'site_lineups', { p_fixture: fixture }, 300_000));
	const cells = (started: XiRow[]): Starter[] => started.map(([pid, name, pos, rank]) => ({ id: pid, name: decodeEntities(name), label: pos || 'CM', rank }));
	const draw = (team: number, opponent: number, home: boolean, kickoff: string, xi: Starter[], note: string) => {
		const hits = xi.filter((c) => c.predicted).length;
		return {
			what: `${teamName(site, team)} ${home ? 'v' : 'at'} ${teamName(site, opponent)} · ${dayName(localDay(kickoff, tz))}`,
			hits, of: xi.length, cls: hits >= 9 ? 'good' : hits >= 7 ? 'ok' : 'poor', bare: !xi.some((c) => c.rank != null), spots: spots(xi), note
		};
	};
	const rec = await quiet(keptDoc<LiveDoc>(fetch, 'lineups', 300_000));
	const live = (rec ? liveRows(rec) : []).filter((x) => known.has(x.team) && fair(x.correct) && x.time > Date.now() - 20 * 864e5).sort((a, b) => b.time - a.time)[0];
	if (live) {
		const fx = await lineups(live.fixture);
		const started = fx?.actual?.[String(live.team)], predicted = fx?.prematch?.[String(live.team)];
		if (started?.length && predicted?.length) {
			const xi = cells(started);
			markPredicted(xi, predicted);
			for (const c of xi) delete c.instead; // no room here for the model's other pick under each miss
			return draw(live.team, live.opponent, !!live.home, live.kickoff, xi, '');
		}
	}
	// the history's rows, newest first: [date, team, opponent, home, competition, right, missed]
	const leagues = [...new Set(top.map((x) => x.league).filter((l) => l != null))];
	const hist = await quiet(keptAsk<HistoryDoc>(fetch, 'site_lineup_history', { p_days: XI_DAYS, p_limit: 300, p_leagues: leagues }, 1_800_000));
	const rows = (hist?.rows || []).filter((x) => known.has(x[1]));
	const r = rows.find((x) => fair(x[5])) || rows.find((x) => x[5] >= XI_RIGHT) || rows[0];
	if (!r) return null;
	const [day, team, opponent, home, , , missed] = r;
	const fixtures = await quiet(clubFixtures(fetch, site, team));
	const m = fixtures?.matches.find((x) => x.home === (home ? team : opponent) && x.away === (home ? opponent : team) && Math.abs(Date.parse(x.kickoff) - Date.parse(day)) < 2 * 864e5);
	const started = m && (await lineups(m.id))?.actual?.[String(team)];
	if (!m || !started?.length) return null;
	const xi = cells(started);
	for (const c of xi) c.predicted = !missed.includes(c.id);
	return draw(team, opponent, !!home, m.kickoff, xi, 'Reconstructed afterwards from pre-match data.');
}

