import { SUPABASE } from '#lib/config.ts';

// Subscriptions are paid through Stripe: its hosted checkout takes the card (no card detail ever
// reaches this site), and its webhook tells this server who has paid, which is written to the
// `subscriptions` table the database's paywall reads. Nothing here is switched on until the
// server has all five secrets (set in Cloudflare, never in the code):
//   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET   Stripe's API key and the webhook's signing secret
//   STRIPE_PRICE_MONTHLY, STRIPE_PRICE_YEARLY  the two prices' ids in Stripe
//   SUPABASE_SERVICE_KEY                       the database key that may write `subscriptions`
export type Payments = { key: string; hook: string; prices: { monthly: string; yearly: string }; db: string };
export function payments(env: Record<string, string | undefined>): Payments | null {
	const { STRIPE_SECRET_KEY: key, STRIPE_WEBHOOK_SECRET: hook, STRIPE_PRICE_MONTHLY: monthly, STRIPE_PRICE_YEARLY: yearly, SUPABASE_SERVICE_KEY: db } = env;
	return key && hook && monthly && yearly && db ? { key, hook, prices: { monthly, yearly }, db } : null;
}

type Fetch = typeof fetch;
// Stripe takes a form, with nested names in brackets: { a: { b: [1] } } is a[b][0]=1
export function formBody(params: Record<string, unknown>, into = new URLSearchParams(), under = ''): URLSearchParams {
	for (const [k, v] of Object.entries(params)) {
		const name = under ? `${under}[${k}]` : k;
		if (v == null) continue;
		if (typeof v === 'object') formBody(v as Record<string, unknown>, into, name);
		else into.append(name, String(v));
	}
	return into;
}
export async function stripe<T>(fetch: Fetch, key: string, method: 'GET' | 'POST' | 'DELETE', path: string, params?: Record<string, unknown>): Promise<T> {
	const r = await fetch(`https://api.stripe.com/v1/${path}`, {
		method,
		headers: { Authorization: `Bearer ${key}`, ...(params ? { 'Content-Type': 'application/x-www-form-urlencoded' } : {}) },
		body: params ? formBody(params) : undefined
	});
	if (!r.ok) throw new Error(`Stripe ${path}: ${r.status}`);
	return (await r.json()) as T;
}

// A webhook is Stripe's only if its signature matches: "t=<when>,v1=<HMAC-SHA256 of 't.body' with
// the signing secret>", and recent (a copied one can't be sent again later).
export async function signedByStripe(body: string, header: string | null, secret: string, now = Date.now(), withinSeconds = 300): Promise<boolean> {
	const parts = (header || '').split(',').map((p) => p.split('='));
	const t = parts.find(([k]) => k === 't')?.[1], given = parts.filter(([k]) => k === 'v1').map(([, v]) => v);
	if (!t || !given.length || Math.abs(now / 1000 - Number(t)) > withinSeconds) return false;
	const enc = new TextEncoder();
	const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
	const mac = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(`${t}.${body}`)))].map((b) => b.toString(16).padStart(2, '0')).join('');
	// compared without stopping at the first difference
	return given.some((g) => g.length === mac.length && [...g].reduce((diff, ch, i) => diff | (ch.charCodeAt(0) ^ mac.charCodeAt(i)), 0) === 0);
}

// What Stripe says of a subscription, as the `subscriptions` table's row. null: nothing to record
// (no account named on it, or a checkout that hasn't been paid).
export type StripeSubscription = {
	id: string; customer: string | { id: string }; status: string; cancel_at_period_end?: boolean; cancel_at?: number | null; current_period_end?: number;
	metadata?: Record<string, string>;
	items?: { data: { current_period_end?: number; price?: { id: string; recurring?: { interval?: string } | null } }[] };
};
export type SubscriptionRow = {
	user_id: string; status: 'active' | 'trialing' | 'past_due' | 'canceled'; plan: 'monthly' | 'yearly' | null; current_period_end: string | null;
	cancel_at_period_end: boolean; provider: 'stripe'; provider_customer: string; provider_subscription: string; updated_at: string;
};
const STATUS: Record<string, SubscriptionRow['status']> = {
	active: 'active', trialing: 'trialing', past_due: 'past_due',
	canceled: 'canceled', unpaid: 'canceled', incomplete_expired: 'canceled', paused: 'canceled'
};
export function subscriptionRow(s: StripeSubscription, prices: Payments['prices'], now = new Date()): SubscriptionRow | null {
	const user_id = s.metadata?.user_id, status = STATUS[s.status];
	if (!user_id || !status) return null;
	const item = s.items?.data[0], price = item?.price;
	const end = item?.current_period_end ?? s.current_period_end;
	const interval = price?.recurring?.interval;
	return {
		user_id, status,
		plan: price?.id === prices.yearly || interval === 'year' ? 'yearly' : price?.id === prices.monthly || interval === 'month' ? 'monthly' : null,
		current_period_end: end ? new Date(end * 1000).toISOString() : null,
		cancel_at_period_end: !!s.cancel_at_period_end || s.cancel_at != null,
		provider: 'stripe', provider_customer: typeof s.customer === 'string' ? s.customer : s.customer.id, provider_subscription: s.id,
		updated_at: now.toISOString()
	};
}

// The table itself: no visitor's key can read or write it, only the server's
const dbHeaders = (key: string) => ({ apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' });
export async function saveSubscription(fetch: Fetch, p: Payments, row: SubscriptionRow): Promise<void> {
	const r = await fetch(`${SUPABASE.url}/rest/v1/subscriptions?on_conflict=user_id`, {
		method: 'POST', headers: { ...dbHeaders(p.db), Prefer: 'resolution=merge-duplicates,return=minimal' }, body: JSON.stringify(row)
	});
	if (!r.ok) throw new Error(`subscriptions: ${r.status}`);
}
export type Kept = { status: string; provider_customer: string | null; provider_subscription: string | null };
export async function keptSubscription(fetch: Fetch, p: Payments, userId: string): Promise<Kept | null> {
	const q = new URLSearchParams({ user_id: `eq.${userId}`, select: 'status,provider_customer,provider_subscription' });
	const r = await fetch(`${SUPABASE.url}/rest/v1/subscriptions?${q}`, { headers: dbHeaders(p.db) });
	if (!r.ok) throw new Error(`subscriptions: ${r.status}`);
	return ((await r.json()) as Kept[])[0] ?? null;
}
