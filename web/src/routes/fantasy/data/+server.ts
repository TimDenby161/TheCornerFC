import { json } from '@sveltejs/kit';
import { SUPABASE } from '#lib/config.ts';
import { FPL_ENTRY } from '#lib/fantasy.ts';

// The fantasy pages' data, for the browser of whoever is signed in. The database answers only the
// site owner (fpl_owner_data checks the visitor's own token); anyone else gets its "no". Its
// answer is passed straight through unread: it is large, and nothing here needs to open it.
export async function GET({ fetch, locals }) {
	const headers = { 'cache-control': 'private, no-store' };
	if (!locals.token) return json({ ok: false }, { headers });
	const r = await fetch(`${SUPABASE.url}/rest/v1/rpc/fpl_owner_data`, {
		method: 'POST',
		headers: { apikey: SUPABASE.key, Authorization: `Bearer ${locals.token}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({ p_entry: FPL_ENTRY })
	}).catch(() => null);
	if (!r?.ok) return json({ ok: false, error: "Couldn't reach the database just now." }, { headers });
	return new Response(r.body, { headers: { ...headers, 'content-type': 'application/json' } });
}
