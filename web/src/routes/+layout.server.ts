import * as env from '$app/env/private';
import { validZone } from '#lib/matchday.ts';
import { siteAsk } from '#lib/server/database.ts';
import { payments } from '#lib/server/payments.ts';

// What the database says of a signed-in visitor's subscription (my_subscription); nothing about
// subscriptions shows unless its paywall is on.
export type Subscription = { paywall: boolean; signed_in: boolean; subscriber: boolean; status: string | null; plan: string | null; renews_at: string | null; ends: boolean };

export async function load({ fetch, locals, cookies }) {
	// the visitor's time zone, for the days and kick-off times the server writes (the page sets
	// this cookie from the browser's own; UK time until it has)
	const tz = validZone(cookies.get('tz')) ? cookies.get('tz')! : 'Europe/London';
	// whether subscriptions can be bought yet (the server has Stripe's keys)
	const pay = !!payments(env);
	if (!locals.user) return { user: null, sub: null, tz, owner: false, pay };
	const sub = await siteAsk<Subscription>(fetch, 'my_subscription', {}, locals.token).catch(() => null);
	// the Fantasy links are in the menu from the start for the browser the owner last used them in
	// (the cookie decides nothing else: the database checks who asks for the pages' data)
	return { user: { email: locals.user.email }, sub, tz, owner: cookies.get('owner') === '1', pay };
}
