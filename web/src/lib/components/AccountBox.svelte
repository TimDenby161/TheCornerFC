<script lang="ts">
	import { enhance, type SubmitFunction } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import BotCheck from './BotCheck.svelte';
	import { longDate } from '#lib/club.ts';
	import { PRICES } from '#lib/config.ts';
	import type { Subscription } from '../../routes/+layout.server.ts';

	// The account box: sign in with Google or an email and password, create an account, reset a
	// password, and for a signed-in visitor their profile, signing out and deleting the account.
	// Each form posts to the account page's actions, so it works before the page's script runs;
	// with the script, the answer comes back into the box without leaving the page.
	type View = 'signin' | 'signup' | 'reset' | 'newpass' | 'note' | 'account' | 'delete' | 'subscribe';
	let { user, sub, start = null, message = '', messageOk = false, onview, onclose }:
		{ user: { email: string } | null; sub: Subscription | null; start?: string | null; message?: string; messageOk?: boolean;
			onview?: (title: string) => void; onclose?: () => void } = $props();

	const TITLES: Record<View, string> = { signin: 'Sign in', signup: 'Create an account', reset: 'Reset your password',
		newpass: 'Choose a new password', note: 'Check your email', account: 'Your profile', delete: 'Delete your account', subscribe: 'Subscribe' };
	// svelte-ignore state_referenced_locally
	let asked = $state<View>((start as View) || 'signin');
	// svelte-ignore state_referenced_locally
	let msg = $state({ text: message, bad: !!message && !messageOk });
	// whether subscriptions can be bought yet
	const pay = $derived(!!page.data.pay);
	let note = $state('');
	let busy = $state(false);
	let check = $state(0); // a new number draws a fresh bot check
	// what is shown: a signed-in visitor sees their profile unless choosing a password or deleting
	const view = $derived<View>(asked === 'subscribe' ? 'subscribe'
		: !user ? (asked === 'delete' || asked === 'account' ? 'signin' : asked)
		: asked === 'newpass' || asked === 'delete' ? asked : 'account');
	$effect(() => onview?.(TITLES[view]));
	const go = (to: View) => { asked = to; msg = { text: '', bad: false }; };
	const here = $derived(page.url.pathname === '/account' ? '/' : page.url.pathname + page.url.search);

	// a form's answer, back in the box
	const sent: SubmitFunction = () => {
		busy = true; msg = { text: '', bad: false };
		return async ({ result }) => {
			busy = false;
			if (result.type === 'redirect') { location.href = result.location; return; } // on to Google, or to Stripe
			if (result.type === 'failure') { check++; msg = { text: String(result.data?.message || 'Something went wrong. Try again in a moment.'), bad: true }; return; }
			if (result.type !== 'success') { check++; msg = { text: 'Something went wrong. Try again in a moment.', bad: true }; return; }
			const done = result.data?.done;
			if (done === 'note') { note = String(result.data?.note || ''); asked = 'note'; return; }
			// who is signed in has changed: every page's data is asked for again, as them
			await invalidateAll();
			if (done === 'newpass') { asked = 'account'; msg = { text: 'Your password has been changed.', bad: false }; }
			else if (done === 'erased') { asked = 'signin'; msg = { text: 'Your account has been deleted.', bad: false }; }
			else { asked = 'signin'; onclose?.(); }
		};
	};
</script>

{#snippet field(name: string, label: string, type: string, autocomplete: 'username' | 'email' | 'current-password' | 'new-password', min: number | undefined = undefined)}
	<label>{label}<input {type} {name} class="table-search" {autocomplete} required minlength={min} /></label>
{/snippet}
{#snippet google()}
	<form method="post" action="/account?/google" use:enhance={sent}>
		<input type="hidden" name="back" value={here} />
		<button type="submit" class="google-btn" disabled={busy}>
			<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" /><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18z" /><path fill="#FBBC05" d="M3.96 10.71a5.41 5.41 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3-2.33z" /><path fill="#EA4335" d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58z" /></svg>
			<span>Continue with Google</span></button>
	</form>
	<div class="account-or">or</div>
{/snippet}
{#snippet link(to: View, label: string)}<button type="button" class="link-btn" onclick={() => go(to)}>{label}</button>{/snippet}
{#snippet failedCheck()}{#key check}<BotCheck failed={(text) => (msg = { text, bad: true })} />{/key}{/snippet}

{#if view === 'signin'}
	{@render google()}
	<form class="account-form" method="post" action="/account?/signin" use:enhance={sent}>
		{@render field('email', 'Email', 'email', 'username')}{@render field('password', 'Password', 'password', 'current-password')}
		{@render failedCheck()}<button type="submit" class="mt-btn" disabled={busy}>Sign in</button>
	</form>
	<div class="account-links">{@render link('signup', 'Create an account')}{@render link('reset', 'Forgotten your password?')}</div>
{:else if view === 'signup'}
	{@render google()}
	<form class="account-form" method="post" action="/account?/signup" use:enhance={sent}>
		{@render field('email', 'Email', 'email', 'email')}{@render field('password', 'Password (8 characters or more)', 'password', 'new-password', 8)}
		{@render failedCheck()}<button type="submit" class="mt-btn" disabled={busy}>Create account</button>
	</form>
	<div class="stats-note">By creating an account you agree to the <a href="/terms" data-sveltekit-reload>terms of use</a> and the <a href="/privacy" data-sveltekit-reload>privacy notice</a>.</div>
	<div class="account-links">{@render link('signin', 'Already have an account? Sign in')}</div>
{:else if view === 'reset'}
	<p class="account-text">Enter your email and we'll send you a link to choose a new password.</p>
	<form class="account-form" method="post" action="/account?/reset" use:enhance={sent}>
		{@render field('email', 'Email', 'email', 'username')}
		{@render failedCheck()}<button type="submit" class="mt-btn" disabled={busy}>Send the link</button>
	</form>
	<div class="account-links">{@render link('signin', 'Back to sign in')}</div>
{:else if view === 'newpass'}
	<form class="account-form" method="post" action="/account?/newpass" use:enhance={sent}>
		{@render field('password', 'New password (8 characters or more)', 'password', 'new-password', 8)}
		<button type="submit" class="mt-btn" disabled={busy}>Save password</button>
	</form>
{:else if view === 'note'}
	<p class="account-text">{note}</p>
	<div class="account-links">{@render link('signin', 'Back to sign in')}</div>
{:else if view === 'subscribe'}
	<p class="account-text">Free for everyone: the model's win, draw and loss chances for every match in the next 7 days, results and the model's record, the club ratings, league tables and the betting comparison pages.</p>
	<p class="account-text">For subscribers: the chances for matches further ahead, the projected score, the key reasons and full model detail behind every prediction, predicted line-ups, every league's projected table with each club's finishing chances, and the full player ranks (the top 50 overall, the top 10 in each league and the top 10 in each position are free).</p>
	{#if !pay}
		<p class="account-text"><b>Subscriptions aren't open yet.</b></p>
	{:else if sub?.subscriber}
		<p class="account-text"><b>This account is subscribed.</b></p>
	{:else if user}
		<p class="account-text">Cancel whenever you like: the subscription then runs to the end of the time paid for. Payment is taken by Stripe; this site never sees your card. See the <a href="/terms" data-sveltekit-reload>terms</a>.</p>
		<form method="post" action="/account?/subscribe" use:enhance={sent} class="account-plans">
			<button type="submit" name="plan" value="monthly" class="mt-btn account-out" disabled={busy}>Subscribe · {PRICES.monthly}</button>
			<button type="submit" name="plan" value="yearly" class="mt-btn account-out" disabled={busy}>Subscribe · {PRICES.yearly}</button>
		</form>
	{:else}
		<p class="account-text"><b>{PRICES.monthly}, or {PRICES.yearly}.</b> Sign in or create a free account first, then subscribe from here.</p>
	{/if}
	<div class="account-links">{@render link(user ? 'account' : 'signin', user ? 'Back to your account' : 'Sign in')}</div>
{:else if view === 'account' && user}
	<p class="account-text">Signed in as <b>{user.email}</b></p>
	{#if sub?.paywall}
		{#if sub.subscriber}
			<p class="account-text">Subscription: <b>{sub.status ? (sub.status === 'past_due' ? 'payment due' : sub.status) : 'active'}</b>{sub.plan ? ` (${sub.plan})` : ''}{sub.renews_at ? ` · ${sub.ends ? 'ends' : 'renews'} ${longDate(sub.renews_at.slice(0, 10))}` : ''}</p>
			{#if pay && sub.status}<form method="post" action="/account?/manage" use:enhance={sent}><button type="submit" class="mt-btn account-out" disabled={busy}>Manage or cancel subscription</button></form>{/if}
		{:else}
			<p class="account-text">No subscription on this account. {@render link('subscribe', 'What subscribers get')}</p>
		{/if}
	{/if}
	<form method="post" action="/account?/signout" use:enhance={sent}><button type="submit" class="mt-btn account-out" disabled={busy}>Sign out</button></form>
	<div class="account-links">{@render link('delete', 'Delete account')}</div>
{:else if view === 'delete' && user}
	<p class="account-text">This deletes your account (<b>{user.email}</b>) and its sign-in details for good. It can't be undone.</p>
	<form method="post" action="/account?/erase" use:enhance={sent}><button type="submit" class="mt-btn account-out account-danger" disabled={busy}>Delete my account</button></form>
	<div class="account-links">{@render link('account', 'Keep my account')}</div>
{/if}
<div class="stats-note" id="account-msg" class:bad={msg.bad} role={msg.bad ? 'alert' : 'status'}>{msg.text}</div>
