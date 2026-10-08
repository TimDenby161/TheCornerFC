import { json } from '@sveltejs/kit';
import { matchDetail } from '#lib/matchDetail.ts';
import { matchBase, matchWhy } from '#lib/server/match.ts';
import { teamName } from '#lib/site.ts';

// A match's model detail, asked for when its card's "Model detail" is opened
export async function GET({ fetch, params, locals }) {
	const { site, m } = await matchBase(fetch, params.id, locals.token);
	const row = await matchWhy(fetch, m.id, locals.token);
	const headers = { 'cache-control': locals.token ? 'private, no-store' : 'public, max-age=60' };
	if (row?.locked) return json({ locked: true }, { headers });
	const x = row?.why ? { ...row.why, model_info: row.model } : null;
	return json(matchDetail(m, x, teamName(site, m.home), teamName(site, m.away)), { headers });
}
