import { defineEnvVars } from '@sveltejs/kit/env';

// The server's secrets, set in Cloudflare (Workers > thecornerfc > Settings > Variables and
// Secrets), never in the code. All five are for taking payment; each may be missing, and until
// all are there subscriptions can't be bought (src/lib/server/payments.ts).
const optional = (description: string) => ({ schema: (v: string | undefined) => v || undefined, description });
export const variables = defineEnvVars({
	STRIPE_SECRET_KEY: optional("Stripe's secret API key"),
	STRIPE_WEBHOOK_SECRET: optional("The signing secret of Stripe's webhook to /stripe/webhook"),
	STRIPE_PRICE_MONTHLY: optional("The monthly price's id in Stripe"),
	STRIPE_PRICE_YEARLY: optional("The yearly price's id in Stripe"),
	SUPABASE_SERVICE_KEY: optional("The database's service key: the only one that may write the subscriptions table")
});
