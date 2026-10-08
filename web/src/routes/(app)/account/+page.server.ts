import { fail, redirect } from '@sveltejs/kit';
import * as env from '$app/env/private';
import { accountError, safePath } from '#lib/server/auth.ts';
import { keptSubscription, payments, stripe } from '#lib/server/payments.ts';

const VIEWS = new Set(['signin', 'signup', 'reset', 'newpass', 'subscribe', 'delete']);

// The account page: the same box the menu's button opens, as a page of its own. It is where a
// form lands when the page's script isn't running, and where an emailed link that failed, or a
// password reset, comes back to.
export function load({ url }) {
	const view = url.searchParams.get('view');
	const failed = url.searchParams.get('failed');
	// back from Stripe's checkout: its webhook switches the subscription on, usually within seconds
	const paid = url.searchParams.has('paid');
	return {
		view: view && VIEWS.has(view) ? view : null,
		message: failed ? accountError({ code: failed }) : paid ? 'Thank you. Your subscription is being switched on: it can take a minute to show here.' : '',
		messageOk: !failed && paid
	};
}

const text = (form: FormData, name: string) => String(form.get(name) ?? '');
// the bot check's answer, which Supabase verifies before it acts (the widget puts it in the form)
const captcha = (form: FormData) => text(form, 'cf-turnstile-response') || undefined;
const NO_CHECK = 'Wait for the check above the button to finish, then try again.';

export const actions = {
	signin: async ({ request, locals }) => {
		const form = await request.formData();
		const email = text(form, 'email').trim(), captchaToken = captcha(form);
		if (!captchaToken) return fail(400, { message: NO_CHECK, email });
		const { error } = await locals.supabase.auth.signInWithPassword({ email, password: text(form, 'password'), options: { captchaToken } });
		if (error) return fail(400, { message: accountError(error), email });
		return { done: 'signin' as const };
	},
	signup: async ({ request, locals, url }) => {
		const form = await request.formData();
		const email = text(form, 'email').trim(), captchaToken = captcha(form);
		if (!captchaToken) return fail(400, { message: NO_CHECK, email });
		const { data, error } = await locals.supabase.auth.signUp({ email, password: text(form, 'password'), options: { emailRedirectTo: `${url.origin}/`, captchaToken } });
		if (error) return fail(400, { message: accountError(error), email });
		// the same answer whether or not the email has an account, so the box can't be used to find out
		return data.session ? { done: 'signin' as const } : { done: 'note' as const, note: `We've sent a link to ${email}. Open it to finish creating your account.` };
	},
	reset: async ({ request, locals, url }) => {
		const form = await request.formData();
		const email = text(form, 'email').trim(), captchaToken = captcha(form);
		if (!captchaToken) return fail(400, { message: NO_CHECK, email });
		const { error } = await locals.supabase.auth.resetPasswordForEmail(email, { redirectTo: `${url.origin}/`, captchaToken });
		if (error) return fail(400, { message: accountError(error), email });
		return { done: 'note' as const, note: `If ${email} has an account, we've sent it a link to choose a new password.` };
	},
	newpass: async ({ request, locals }) => {
		if (!locals.user) return fail(401, { message: 'That link has expired or has already been used. Ask for a new one.' });
		const form = await request.formData();
		const { error } = await locals.supabase.auth.updateUser({ password: text(form, 'password') });
		if (error) return fail(400, { message: accountError(error) });
		return { done: 'newpass' as const };
	},
	// on to Google, which sends the visitor back to the page they were on
	google: async ({ request, locals, url }) => {
		const form = await request.formData();
		const back = safePath(text(form, 'back'));
		const { data, error } = await locals.supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${url.origin}${back}`, skipBrowserRedirect: true } });
		if (error || !data.url) return fail(400, { message: accountError(error) });
		redirect(303, data.url);
	},
	// this browser only
	signout: async ({ locals }) => {
		const { error } = await locals.supabase.auth.signOut({ scope: 'local' });
		if (error) return fail(400, { message: accountError(error) });
		return { done: 'signout' as const };
	},
	// removes the caller's own row from Supabase Auth and nothing else (delete_my_account)
	erase: async ({ locals, fetch }) => {
		if (!locals.user) return fail(401, { message: 'Sign in first.' });
		// a subscription still running is cancelled with Stripe first, so nothing more is charged
		const p = payments(env);
		if (p) {
			try {
				const kept = await keptSubscription(fetch, p, locals.user.id);
				if (kept?.provider_subscription && kept.status !== 'canceled') await stripe(fetch, p.key, 'DELETE', `subscriptions/${encodeURIComponent(kept.provider_subscription)}`);
			} catch {
				return fail(502, { message: "Your subscription couldn't be cancelled just now, so the account has been kept. Try again in a moment." });
			}
		}
		const { error } = await locals.supabase.rpc('delete_my_account');
		if (error) return fail(400, { message: accountError(error) });
		await locals.supabase.auth.signOut({ scope: 'local' });
		return { done: 'erased' as const };
	},
	// On to Stripe's checkout for the plan picked. The subscription it starts carries this
	// account's id, which is how the webhook knows whose it is.
	subscribe: async ({ request, locals, fetch, url }) => {
		const p = payments(env);
		if (!p) return fail(400, { message: "Subscriptions aren't open yet." });
		if (!locals.user) return fail(401, { message: 'Sign in first.' });
		const plan = text(await request.formData(), 'plan') === 'yearly' ? 'yearly' : 'monthly';
		let to: string;
		try {
			const kept = await keptSubscription(fetch, p, locals.user.id);
			if (kept && kept.status !== 'canceled') return fail(400, { message: 'This account already has a subscription.' });
			const session = await stripe<{ url: string }>(fetch, p.key, 'POST', 'checkout/sessions', {
				mode: 'subscription', line_items: [{ price: p.prices[plan], quantity: 1 }],
				client_reference_id: locals.user.id, subscription_data: { metadata: { user_id: locals.user.id } },
				// a returning subscriber keeps their record with Stripe
				...(kept?.provider_customer ? { customer: kept.provider_customer } : { customer_email: locals.user.email }),
				success_url: `${url.origin}/account?paid=1`, cancel_url: `${url.origin}/account?view=subscribe`
			});
			to = session.url;
		} catch {
			return fail(502, { message: "The checkout couldn't be opened just now. Try again in a moment." });
		}
		redirect(303, to);
	},
	// On to Stripe's own page for a subscriber: change the card, see invoices, cancel
	manage: async ({ locals, fetch, url }) => {
		const p = payments(env);
		if (!p) return fail(400, { message: "Subscriptions aren't open yet." });
		if (!locals.user) return fail(401, { message: 'Sign in first.' });
		let to: string;
		try {
			const kept = await keptSubscription(fetch, p, locals.user.id);
			if (!kept?.provider_customer) return fail(400, { message: 'No subscription on this account.' });
			to = (await stripe<{ url: string }>(fetch, p.key, 'POST', 'billing_portal/sessions', { customer: kept.provider_customer, return_url: `${url.origin}/account` })).url;
		} catch {
			return fail(502, { message: "That page couldn't be opened just now. Try again in a moment." });
		}
		redirect(303, to);
	}
};
