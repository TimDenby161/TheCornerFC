import { describe, expect, it } from 'vitest';
import { formBody, payments, signedByStripe, subscriptionRow, type StripeSubscription } from './payments';

const PRICES = { monthly: 'price_m', yearly: 'price_y' };
const KNOWN = '6624ddd652ee78d27211f2d32373bb1b7277e4d2b5af8aff64cac0580f3e651f';
describe('payments', () => {
	it('are off until every secret is set', () => {
		expect(payments({})).toBeNull();
		expect(payments({ STRIPE_SECRET_KEY: 'sk', STRIPE_WEBHOOK_SECRET: 'wh', STRIPE_PRICE_MONTHLY: 'm', STRIPE_PRICE_YEARLY: 'y' })).toBeNull();
		expect(payments({ STRIPE_SECRET_KEY: 'sk', STRIPE_WEBHOOK_SECRET: 'wh', STRIPE_PRICE_MONTHLY: 'm', STRIPE_PRICE_YEARLY: 'y', SUPABASE_SERVICE_KEY: 'db' }))
			.toEqual({ key: 'sk', hook: 'wh', prices: { monthly: 'm', yearly: 'y' }, db: 'db' });
	});
	it("write Stripe's forms with nested names in brackets", () => {
		expect(formBody({ mode: 'subscription', line_items: [{ price: 'p', quantity: 1 }], subscription_data: { metadata: { user_id: 'u' } }, skip: undefined }).toString())
			.toBe('mode=subscription&line_items%5B0%5D%5Bprice%5D=p&line_items%5B0%5D%5Bquantity%5D=1&subscription_data%5Bmetadata%5D%5Buser_id%5D=u');
	});
	it("take a webhook only with Stripe's signature, and only a recent one", async () => {
		const body = '{"type":"x"}', secret = 'whsec_test', t = 1_800_000_000;
		const enc = new TextEncoder(), key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
		const sig = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(`${t}.${body}`)))].map((b) => b.toString(16).padStart(2, '0')).join('');
		// (a known answer, so the check isn't only of the code against itself)
		expect(sig).toBe(KNOWN);
		expect(await signedByStripe(body, `t=${t},v1=${sig}`, secret, t * 1000 + 5000)).toBe(true);
		expect(await signedByStripe(body, `t=${t},v1=bad,v1=${sig}`, secret, t * 1000)).toBe(true);
		expect(await signedByStripe(body + ' ', `t=${t},v1=${sig}`, secret, t * 1000)).toBe(false);
		expect(await signedByStripe(body, `t=${t},v1=${sig}`, 'other', t * 1000)).toBe(false);
		expect(await signedByStripe(body, `t=${t},v1=${sig}`, secret, (t + 301) * 1000)).toBe(false);
		expect(await signedByStripe(body, null, secret, t * 1000)).toBe(false);
		expect(await signedByStripe(body, `v1=${sig}`, secret, t * 1000)).toBe(false);
	});
	it("turn Stripe's subscription into the table's row", () => {
		const s: StripeSubscription = { id: 'sub_1', customer: 'cus_1', status: 'active', cancel_at_period_end: false, metadata: { user_id: 'u1' },
			items: { data: [{ current_period_end: 1_800_000_000, price: { id: 'price_y', recurring: { interval: 'year' } } }] } };
		const now = new Date('2026-10-08T12:00:00Z');
		expect(subscriptionRow(s, PRICES, now)).toEqual({ user_id: 'u1', status: 'active', plan: 'yearly', current_period_end: '2027-01-15T08:00:00.000Z',
			cancel_at_period_end: false, provider: 'stripe', provider_customer: 'cus_1', provider_subscription: 'sub_1', updated_at: '2026-10-08T12:00:00.000Z' });
		// older API versions keep the period's end on the subscription; a customer may come whole
		expect(subscriptionRow({ ...s, items: { data: [{ price: { id: 'price_m' } }] }, current_period_end: 1_800_000_000, customer: { id: 'cus_2' } }, PRICES, now))
			.toMatchObject({ plan: 'monthly', current_period_end: '2027-01-15T08:00:00.000Z', provider_customer: 'cus_2' });
		expect(subscriptionRow({ ...s, status: 'past_due' }, PRICES)?.status).toBe('past_due');
		expect(subscriptionRow({ ...s, status: 'unpaid' }, PRICES)?.status).toBe('canceled');
		expect(subscriptionRow({ ...s, cancel_at: 1_800_000_000 }, PRICES)?.cancel_at_period_end).toBe(true);
		// a checkout not yet paid, or a subscription naming no account: nothing to record
		expect(subscriptionRow({ ...s, status: 'incomplete' }, PRICES)).toBeNull();
		expect(subscriptionRow({ ...s, metadata: {} }, PRICES)).toBeNull();
	});
});
