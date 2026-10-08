import { createServerClient } from '@supabase/ssr';
import type { RequestEvent } from '@sveltejs/kit';
import { SUPABASE } from '#lib/config.ts';

// Sign-in is the server's job. The session (Supabase Auth's access and refresh tokens) lives in a
// cookie the page's scripts can't read (HttpOnly), sent only to this site over HTTPS; nothing
// about it is kept in the browser's storage. The library refreshes it and writes the cookie back.
export function supabaseFor(event: RequestEvent) {
	return createServerClient(SUPABASE.url, SUPABASE.key, {
		auth: { flowType: 'pkce' },
		cookieOptions: { httpOnly: true, secure: event.url.protocol === 'https:', sameSite: 'lax', path: '/' },
		cookies: {
			getAll: () => event.cookies.getAll(),
			setAll: (list) => {
				for (const { name, value, options } of list) event.cookies.set(name, value, { ...options, path: '/' });
			}
		}
	});
}

// What went wrong, in words. The same answer whether or not an email has an account, wherever
// the service allows it, so the forms can't be used to find out.
export function accountError(err: { code?: string; status?: number; name?: string } | null | undefined): string {
	if (err?.name === 'AuthRetryableFetchError') return "Couldn't reach the sign-in service just now. Check your connection and try again.";
	if (err?.status === 429) return 'Too many tries. Wait a minute, then try again.';
	const known: Record<string, string> = {
		invalid_credentials: "That email and password don't match an account.",
		email_not_confirmed: 'Confirm your email first: open the link we sent you.',
		user_already_exists: "There's already an account for that email. Sign in instead.",
		weak_password: 'That password is too easy to guess. Choose a longer one.',
		captcha_failed: "The check that you're not a bot didn't pass. Try again.",
		same_password: "That's already your password. Choose a different one.",
		otp_expired: 'That link has expired or has already been used. Ask for a new one.',
		flow_state_not_found: 'That link has expired or has already been used. Ask for a new one.',
		flow_state_expired: 'That link has expired or has already been used. Ask for a new one.',
		// Supabase's default emailed link, or a Google sign-in, finished in a browser other than the one that began it
		pkce_code_verifier_not_found: "That link was opened in a different browser from the one that asked for it. If you were confirming your email, it's confirmed: sign in here. If you were resetting your password, ask for a new link from this browser."
	};
	return (err?.code && known[err.code]) || 'Something went wrong. Try again in a moment.';
}

// An address on this site to go back to after signing in: a path of ours, never somewhere else
export const safePath = (to: string | null | undefined) => (to && /^\/(?!\/)[\w\-./?=&%:|,+]*$/.test(to) ? to : '/');
