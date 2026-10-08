import { isRedirect, redirect } from '@sveltejs/kit';
import { expect, it } from 'vitest';

// The framework refuses a redirect to another site unless it is told which sites are allowed
// (found the hard way: www and Google sign-in answered "Internal Error"). These are the forms the
// app uses; each must come out as a redirect, not an error.
const goes = (to: string, external: string[]) => { try { redirect(303, to, { external }); } catch (e) { return isRedirect(e) ? e.location : String(e); } };
it('lets the app send a visitor on to the sites it names, and nowhere else', () => {
	expect(goes('https://thecornerfc.com/clubs?c=39', ['https://thecornerfc.com'])).toBe('https://thecornerfc.com/clubs?c=39');
	expect(goes('https://bookkurhdabdeccckjbn.supabase.co/auth/v1/authorize?provider=google', ['https://bookkurhdabdeccckjbn.supabase.co', 'https://accounts.google.com'])).toContain('/auth/v1/authorize');
	expect(goes('https://checkout.stripe.com/c/pay/cs_test_1', ['https://checkout.stripe.com'])).toContain('checkout.stripe.com');
	expect(isRedirectTo('https://evil.example/x', ['https://checkout.stripe.com'])).toBe(false);
});
function isRedirectTo(to: string, external: string[]) { try { redirect(303, to, { external }); } catch (e) { return isRedirect(e); } return false; }
