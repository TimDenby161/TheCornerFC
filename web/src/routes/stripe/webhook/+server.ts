import { error, json } from '@sveltejs/kit';
import * as env from '$app/env/private';
import { payments, saveSubscription, signedByStripe, stripe, subscriptionRow, type StripeSubscription } from '#lib/server/payments.ts';

// Stripe calls this when a subscription starts, renews, fails to renew, is cancelled or ends. Each
// call is checked to be Stripe's, then what Stripe now says of that subscription is written to
// the `subscriptions` table: the database's paywall reads nothing else. Always from Stripe's own
// current record (asked for afresh), so calls arriving out of order can't leave an old state.
const EVENTS = new Set(['checkout.session.completed', 'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted',
	'customer.subscription.paused', 'customer.subscription.resumed']);
export async function POST({ request, fetch }) {
	const p = payments(env);
	if (!p) error(404, 'Not found');
	const body = await request.text();
	if (!(await signedByStripe(body, request.headers.get('stripe-signature'), p.hook))) error(400, 'Bad signature');
	const event = JSON.parse(body) as { type: string; data: { object: { id: string; subscription?: string | null } } };
	if (!EVENTS.has(event.type)) return json({ received: true });
	const id = event.type === 'checkout.session.completed' ? event.data.object.subscription : event.data.object.id;
	if (!id) return json({ received: true });
	// a failure here answers 500, and Stripe sends the event again later
	const sub = await stripe<StripeSubscription>(fetch, p.key, 'GET', `subscriptions/${encodeURIComponent(id)}`);
	const row = subscriptionRow(sub, p.prices);
	if (row) await saveSubscription(fetch, p, row);
	return json({ received: true });
}
