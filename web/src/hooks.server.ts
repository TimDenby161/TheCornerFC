import { error, redirect } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit/hooks';
import { SITE_ENV, SITE_HOST } from '#lib/config.ts';
import { oldFile, tabFor } from '#lib/menu.ts';
import { adminGate, isAdminPath } from '#lib/server/admin.ts';
import { supabaseFor } from '#lib/server/auth.ts';

const LINK_TYPES = new Set(['signup', 'email', 'recovery', 'magiclink', 'invite', 'email_change']);

export const handle: Handle = async ({ event, resolve }) => {
	// This code was built for one environment and its Worker is set up as one (SITE_ENV in
	// wrangler.jsonc). If the two differ, a staging build has reached the live Worker or the other
	// way round: serve nothing.
	const deployed = event.platform?.env;
	if (deployed && deployed.SITE_ENV !== SITE_ENV) error(500, 'This build is not for this site');

	// www is the same site: one address for it. And the old site's files by their old names
	// (/terms.html) go to the page here; the part after a # is kept by the browser.
	// (and the site's address without https goes to it with)
	if (event.url.hostname === SITE_HOST && event.url.protocol === 'http:') redirect(301, `https://${SITE_HOST}${event.url.pathname}${event.url.search}`, { external: [`https://${SITE_HOST}`] });
	if (event.url.hostname === `www.${SITE_HOST}`) redirect(301, `https://${SITE_HOST}${event.url.pathname}${event.url.search}`, { external: [`https://${SITE_HOST}`] });
	const moved = oldFile(event.url.pathname);
	if (moved) redirect(301, moved + event.url.search);

	const supabase = (event.locals.supabase = supabaseFor(event));
	const q = event.url.searchParams;

	// Coming back from an emailed link (?token_hash=&type=, the form the email templates use, which
	// works in any browser) or from Google (?code=): finish the sign-in, then show the same address
	// without those. A link that has expired or been used opens the account page saying so.
	if (event.request.method === 'GET' && (q.has('token_hash') || q.has('code') || q.has('error_description'))) {
		const to = new URL(event.url);
		for (const k of ['code', 'token_hash', 'type', 'error', 'error_code', 'error_description']) to.searchParams.delete(k);
		let failed: string | null = q.has('error_description') ? q.get('error_code') || 'error' : null;
		let recovery = false;
		if (!failed && q.has('token_hash') && LINK_TYPES.has(q.get('type') || '')) {
			const type = q.get('type') as 'email';
			const { error } = await supabase.auth.verifyOtp({ token_hash: q.get('token_hash')!, type });
			failed = error ? error.code || 'error' : null;
			recovery = q.get('type') === 'recovery';
		} else if (!failed && q.has('code')) {
			const { error } = await supabase.auth.exchangeCodeForSession(q.get('code')!);
			failed = error ? error.code || 'error' : null;
		}
		if (failed) redirect(303, `/account?failed=${encodeURIComponent(failed)}`);
		redirect(303, recovery ? '/account?view=newpass' : to.pathname + to.search);
	}

	// Who is signed in, if anyone. The token is what the database checks for itself on every
	// request it is sent with, so nothing here decides what a visitor may see.
	const { data: { session } } = await supabase.auth.getSession();
	if (session?.user?.email) {
		event.locals.user = { id: session.user.id, email: session.user.email };
		event.locals.token = session.access_token;
	}

	// The Admin area, every address under /admin (pages, the data behind them, anything added
	// later): checked here, before any of it runs, and by the database, not by this code. A
	// visitor who isn't signed in is sent to sign in; one who is and isn't an administrator is
	// told there is no such page. The documents themselves are refused by the database again.
	const gate = await adminGate(event.fetch, event.url.pathname, event.locals.token);
	if (gate === 'signin') redirect(303, '/account');
	if (gate === 'refuse') error(404, 'Not found');
	if (gate === 'admin') event.locals.admin = true;

	const response = await resolve(event, {
		// the stylesheet lays a section out by the name on <body data-tab>, so the server writes it
		transformPageChunk: ({ html }) => html.replace('%tab%', tabFor(event.url.pathname)),
		filterSerializedResponseHeaders: (name) => name === 'content-range' || name === 'x-supabase-api-version'
	});
	// a page differs by who asks: nothing may hand one visitor's copy to another, and a signed-in
	// visitor's is never kept
	response.headers.append('vary', 'Cookie');
	// staging is never for search engines, whatever links to it
	if (SITE_ENV !== 'production') response.headers.set('x-robots-tag', 'noindex, nofollow');
	if (event.locals.user || isAdminPath(event.url.pathname)) response.headers.set('cache-control', 'private, no-store');
	return response;
};
