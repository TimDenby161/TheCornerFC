import { error } from '@sveltejs/kit';
import { matchRows, type Match, type MatchesAnswer } from '#lib/matches.ts';
import type { Why } from '#lib/matchDetail.ts';
import type { Site } from '#lib/site.ts';
import { askAs, keptDoc } from './database.ts';

// One match by its id, as this visitor may see it (`paywall`: the database held paid fields back)
export async function matchBase(fetch: typeof globalThis.fetch, param: string, token?: string) {
	if (!/^\d{1,10}$/.test(param)) error(404, 'Not found');
	const site = await keptDoc<Site>(fetch, 'site');
	const answer = await askAs<MatchesAnswer>(fetch, token, 'site_matches', { p_ids: [Number(param)] });
	const m: Match | undefined = matchRows(site.match_fields, answer)[0];
	if (!m) error(404, 'Not found');
	return { site, m, paywall: !!answer.paywall };
}
// Its stored explanation (site_match_detail), with the model version that made it by name
export type DetailAnswer = { why: Why | null; model?: { name?: string; code?: string } | null; locked?: boolean } | null;
export const matchWhy = (fetch: typeof globalThis.fetch, id: number, token?: string) =>
	askAs<DetailAnswer>(fetch, token, 'site_match_detail', { p_fixture: id }).catch(() => null);
