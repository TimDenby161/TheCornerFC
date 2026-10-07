import { json } from '@sveltejs/kit';
import { playersBase, playersPage } from '#lib/server/players.ts';

// The next rows of the Players list, as it is scrolled: the page's own address with ?offset=
export async function GET({ fetch, url }) {
	const offset = Math.max(0, Math.min(100_000, Number(url.searchParams.get('offset')) || 0));
	const { rows } = await playersPage(fetch, await playersBase(fetch, url.searchParams), offset);
	return json({ rows }, { headers: { 'cache-control': 'public, max-age=60' } });
}
