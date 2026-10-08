import { FLAG_CODES } from '#lib/names.ts';
import { nationBase } from '#lib/server/nation.ts';

export async function load({ fetch, params, locals, setHeaders }) {
	const { name, team, spell, rating } = await nationBase(fetch, params.name, locals.token);
	if (!locals.token) setHeaders({ 'cache-control': 'public, max-age=60' });
	return { name, flag: FLAG_CODES[name] ?? null, coach: spell?.coach ?? null, rating, hasTeam: !!team };
}
