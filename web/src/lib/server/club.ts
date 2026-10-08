import { error } from '@sveltejs/kit';
import { clubMatches, type ClubDoc } from '#lib/club.ts';
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
