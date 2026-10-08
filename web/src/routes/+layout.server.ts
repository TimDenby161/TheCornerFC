import { siteAsk } from '#lib/server/database.ts';

// What the database says of a signed-in visitor's subscription (my_subscription); nothing about
// subscriptions shows unless its paywall is on.
export type Subscription = { paywall: boolean; signed_in: boolean; subscriber: boolean; status: string | null; plan: string | null; renews_at: string | null; ends: boolean };

export async function load({ fetch, locals }) {
	if (!locals.user) return { user: null, sub: null };
	const sub = await siteAsk<Subscription>(fetch, 'my_subscription', {}, locals.token).catch(() => null);
	return { user: { email: locals.user.email }, sub };
}
