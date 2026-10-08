import { redirect } from '@sveltejs/kit';
import { leagueBase } from '#lib/server/league.ts';

// A competition's own address opens its standings, or, for a cup without a table, its matches
export async function load({ fetch, params, locals }) {
	const { id, table } = await leagueBase(fetch, params.id, locals.token);
	redirect(307, `/league/${id}/${table.length ? 'table' : 'matches'}`);
}
