import { error } from '@sveltejs/kit';
import { clubMatches, clubSeasons, type ClubDoc } from '#lib/club.ts';
import { clubDepth, type Starts } from '#lib/depth.ts';
import { upcoming } from '#lib/matches.ts';
import { playerRows, type PlayersAnswer } from '#lib/players.ts';
import { matchRows, type MatchesAnswer } from '#lib/matches.ts';
import { clubs, type RankingsDoc } from '#lib/rankings.ts';
import { teamName, type Site } from '#lib/site.ts';
import { askAs, keptDoc, keptDocOrNull } from './database.ts';

// What every part of a club's page starts from: the names, every club's ratings, and this club's
// own file. A club neither the names nor the ratings know, with no file, has no page.
export async function clubBase(fetch: typeof globalThis.fetch, param: string) {
	if (!/^\d{1,9}$/.test(param)) error(404, 'Not found');
	const id = Number(param);
	const [site, rankings, doc] = await Promise.all([
		keptDoc<Site>(fetch, 'site'),
		keptDoc<RankingsDoc>(fetch, 'rankings'),
		keptDocOrNull<ClubDoc>(fetch, `clubs/${id}`)
	]);
	const all = clubs(rankings);
	const rank = all.find((c) => c.team === id) ?? null;
	if (!doc && !rank && site.teams[id] == null) error(404, 'Not found');
	const rows = clubMatches(doc);
	// an opponent's name as the club's file has it (clubs the names row doesn't hold), else the site's
	const opponent = (o: number) => doc?.teams?.[o] || teamName(site, o);
	return { id, site, all, rank, doc, rows, opponent, name: teamName(site, id) };
}

// The club's matches from the matches table, oldest first, as this visitor may see them (`token`:
// theirs, if signed in); `paywall`: the database left the paid fields of matches to come out.
export async function clubFixtures(fetch: typeof globalThis.fetch, site: Site, id: number, token?: string) {
	const answer = await askAs<MatchesAnswer>(fetch, token, 'site_matches', { p_team: id });
	return { matches: matchRows(site.match_fields, answer), paywall: !!answer.paywall };
}

// The injury lists: per club, its next match's, else its latest recent one. A row is
// [player, name, type, ban, matches missed in a row, season rank]; the injury itself isn't published.
export type Injuries = { teams: Record<string, { kickoff: string; upcoming: boolean; players: [number, string, string, string | null, number, number | null][] }> };
export const clubInjuries = (fetch: typeof globalThis.fetch, id: number) =>
	keptDoc<Injuries>(fetch, 'injuries', 300_000).then((d) => d.teams?.[String(id)] ?? null, () => null);

// Everyone listed at the club, as this visitor may see them (a visitor who isn't a subscriber
// gets the players outside the free slice with their ranks blanked: `paywall`)
export async function clubPlayers(fetch: typeof globalThis.fetch, site: Site, id: number, token?: string) {
	const answer = await askAs<PlayersAnswer>(fetch, token, 'site_players', { p_teams: [id], p_limit: 2000 });
	const list = playerRows(site, answer.rows).filter((p) => p.team === id);
	return { list, paywall: !!answer.paywall || list.some((p) => p.locked) };
}

// The squad by position for the club's next match (depth.ts), with what it was worked out from
// (`forLeague`: work it out for a match in that competition, not the club's own next one)
export async function clubSquad(fetch: typeof globalThis.fetch, base: Awaited<ReturnType<typeof clubBase>>, token?: string, forLeague?: number) {
	const { id, site, doc, rows } = base;
	const [{ list, paywall: locked }, inj, fixtures] = await Promise.all([clubPlayers(fetch, site, id, token), clubInjuries(fetch, id), clubFixtures(fetch, site, id, token)]);
	const next = upcoming(fixtures.matches)[0] ?? null;
	const groupOf = (lg: number) => { const c = site.competitions[lg]; return !c ? 'cup' : c.type === 'League' ? 'league' : c.country === 'World' ? 'europe' : 'cup'; };
	const { seasonOf } = clubSeasons(rows);
	const season = rows.length ? seasonOf(rows[rows.length - 1]) : null;
	const more = doc as (ClubDoc & { starts?: Starts; positions?: Record<string, [string, number][]> }) | null;
	const depth = clubDepth({
		squad: list, out: new Set((inj?.players || []).map(([pid]) => pid)),
		starts: more?.starts, positions: more?.positions,
		seasonFormations: rows.filter((m) => seasonOf(m) === season).map((m) => m.formation),
		nextGroup: forLeague != null ? groupOf(forLeague) : next ? groupOf(next.league) : null, groupOf
	});
	return { depth, list, inj, next, matches: fixtures.matches, paywall: locked || fixtures.paywall, kit: /^[0-9a-f]{6}$/i.test(doc?.colors?.[0] ?? '') ? [doc!.colors![0], /^[0-9a-f]{6}$/i.test(doc!.colors![1] ?? '') ? doc!.colors![1] : 'ffffff'] : null };
}
