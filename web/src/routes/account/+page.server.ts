import { fail, redirect } from '@sveltejs/kit';
import { accountError, safePath } from '#lib/server/auth.ts';

const VIEWS = new Set(['signin', 'signup', 'reset', 'newpass', 'subscribe', 'delete']);

// The account page: the same box the menu's button opens, as a page of its own. It is where a
// form lands when the page's script isn't running, and where an emailed link that failed, or a
// password reset, comes back to.
export function load({ url }) {
	const view = url.searchParams.get('view');
	const failed = url.searchParams.get('failed');
	return { view: view && VIEWS.has(view) ? view : null, message: failed ? accountError({ code: failed }) : '' };
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
	erase: async ({ locals }) => {
		if (!locals.user) return fail(401, { message: 'Sign in first.' });
		const { error } = await locals.supabase.rpc('delete_my_account');
		if (error) return fail(400, { message: accountError(error) });
		await locals.supabase.auth.signOut({ scope: 'local' });
		return { done: 'erased' as const };
	}
};
