import { SUPABASE } from '#lib/config.ts';

// Every read of the database goes through here, on the server. `fetch` is the request's own (so
// SvelteKit can follow it); the tests pass a stand-in.
type Fetch = typeof fetch;

export class DatabaseError extends Error {
	constructor(
		what: string,
		public status: number,
		public missing = false
	) {
		super(`${what}: ${status}`);
	}
}

// A request that fails outright or with a server error (a dropped connection, a busy moment) is
// sent once more after a moment before the page gives up.
async function ask(send: () => Promise<Response>, wait = 400): Promise<Response> {
	for (let again = false; ; again = true) {
		try {
			const r = await send();
			if (r.status < 500 || again) return r;
		} catch (err) {
			if (again) throw err;
		}
		await new Promise((done) => setTimeout(done, wait));
	}
}

// One row of site.docs by its key ("rankings", "clubs/42"). A key with no row answers null, which
// is this site's "not found".
export async function siteDoc<T>(fetch: Fetch, key: string, wait?: number): Promise<T> {
	const q = new URLSearchParams({ p_key: key, apikey: SUPABASE.key });
	const r = await ask(() => fetch(`${SUPABASE.url}/rest/v1/rpc/site_doc?${q}`), wait);
	if (!r.ok) throw new DatabaseError(key, r.status);
	const doc = await r.json();
	if (doc === null) throw new DatabaseError(key, 404, true);
	return doc as T;
}

// A database function that answers one page's question from the tables themselves (site_matches,
// site_players ...). `token` is a signed-in visitor's, so the database can give a subscriber the
// paid rows.
export async function siteAsk<T>(
	fetch: Fetch,
	fn: string,
	params: Record<string, string>,
	token?: string
): Promise<T> {
	const r = await ask(() =>
		fetch(`${SUPABASE.url}/rest/v1/rpc/${fn}`, {
			method: 'POST',
			headers: {
				apikey: SUPABASE.key,
				'Content-Type': 'application/json',
				...(token ? { Authorization: `Bearer ${token}` } : {})
			},
			body: JSON.stringify(params)
		})
	);
	if (!r.ok) throw new DatabaseError(fn, r.status);
	return (await r.json()) as T;
}

// Rows that every page needs and that change a few times a day at most are kept for a minute, so
// a busy moment is one read of the database and not one per visitor.
const kept = new Map<string, { at: number; doc: Promise<unknown> }>();
export function keptDoc<T>(fetch: Fetch, key: string, forMs = 60_000): Promise<T> {
	const have = kept.get(key);
	if (have && Date.now() - have.at < forMs) return have.doc as Promise<T>;
	const doc = siteDoc<T>(fetch, key);
	kept.set(key, { at: Date.now(), doc });
	doc.catch(() => kept.delete(key));
	return doc;
}
