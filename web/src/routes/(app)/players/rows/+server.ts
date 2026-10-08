import { json } from '@sveltejs/kit';
import { playersBase, playersPage } from '#lib/server/players.ts';

// The next rows of the Players list, as it is scrolled: the page's own address with ?offset=
export async function GET({ fetch, url, locals }) {
	const offset = Math.max(0, Math.min(100_000, Number(url.searchParams.get('offset')) || 0));
	const { rows } = await playersPage(fetch, await playersBase(fetch, url.searchParams), offset, locals.token);
	return json({ rows }, { headers: { 'cache-control': locals.token ? 'private, no-store' : 'public, max-age=60' } });
}
