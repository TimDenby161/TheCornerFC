import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { longDate } from '../../../web/src/lib/club.ts';

// The account box (AccountBox.svelte and the layout's box): sign in with Google or an email and
// password, create an account, reset a password, and for a signed-in visitor their profile, signing
// out and deleting the account. It opens over the page from the menu's button and from any "What
// subscribers get" link; without this script those are links to the account page, where the same
// forms work on their own. Each form posts to the account page, asking for its answer as JSON.

type View = 'signin' | 'signup' | 'reset' | 'newpass' | 'note' | 'account' | 'delete' | 'subscribe';
type Sub = { paywall: boolean; subscriber: boolean; status: string | null; plan: string | null; renewsAt: string | null; ends: boolean } | null;
export type AccountProps = { user: { email: string } | null; sub: Sub; botCheck: string; pay: boolean; prices: { monthly: string; yearly: string } };
type Answer = { type: 'success'; data: { done: string; note?: string } } | { type: 'failure'; data: { message: string } } | { type: 'redirect'; location: string };

const TITLES: Record<View, string> = {
	signin: 'Sign in', signup: 'Create an account', reset: 'Reset your password', newpass: 'Choose a new password',
	note: 'Check your email', account: 'Your profile', delete: 'Delete your account', subscribe: 'Subscribe'
};

// ---- The check that a visitor isn't a bot (Cloudflare Turnstile, BotCheck.svelte). Its script is
// asked for only when a form that needs it is first shown; the widget writes its answer into the
// form (cf-turnstile-response). An answer passes once: the box draws a fresh check after a failed try.
type Turnstile = { render: (el: HTMLElement, o: Record<string, unknown>) => string; remove: (id: string) => void };
let lib: Promise<Turnstile> | undefined;
const loadTurnstile = () => (lib ||= new Promise<Turnstile>((resolve, reject) => {
	const s = document.createElement('script');
	s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
	s.onload = () => resolve((window as unknown as { turnstile: Turnstile }).turnstile);
	s.onerror = () => { lib = undefined; s.remove(); reject(new Error('bot-check')); };
	document.head.append(s);
}));
function BotCheck({ sitekey, failed }: { sitekey: string; failed: (message: string) => void }) {
	const box = useRef<HTMLDivElement>(null);
	useEffect(() => {
		let id: string | undefined, gone = false;
		// (its usual box is 300px wide: on the smallest phones it draws its narrow one, which fits the form)
		loadTurnstile().then((t) => { if (!gone && box.current) id = t.render(box.current, { sitekey, size: matchMedia('(max-width: 359px)').matches ? 'compact' : 'normal' }); })
			.catch(() => failed("Couldn't load the check that you're not a bot. Check your connection, or try without a content blocker."));
		return () => { gone = true; if (id != null) (window as unknown as { turnstile?: Turnstile }).turnstile?.remove(id); };
	}, [sitekey, failed]);
	return <div id="account-botcheck" ref={box}></div>;
}

const GOOGLE = (
	<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" /><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18z" /><path fill="#FBBC05" d="M3.96 10.71a5.41 5.41 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3-2.33z" /><path fill="#EA4335" d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58z" /></svg>
);

export function AccountBox({ user, sub, botCheck, pay, prices, start, onview, onclose }: AccountProps & { start: View | null; onview: (title: string) => void; onclose: () => void }) {
	const [asked, setAsked] = useState<View>(start || 'signin');
	const [msg, setMsg] = useState({ text: '', bad: false });
	const [note, setNote] = useState('');
	const [busy, setBusy] = useState(false);
	const [check, setCheck] = useState(0); // a new number draws a fresh bot check
	const [who, setWho] = useState(user);
	// what is shown: a signed-in visitor sees their profile unless choosing a password or deleting
	const view: View = asked === 'subscribe' ? 'subscribe' : asked === 'note' ? 'note'
		: !who ? (asked === 'delete' || asked === 'account' ? 'signin' : asked)
		: asked === 'newpass' || asked === 'delete' ? asked : 'account';
	useEffect(() => onview(TITLES[view]), [view, onview]);
	const go = (to: View) => { setAsked(to); setMsg({ text: '', bad: false }); };
	const failed = useRef((text: string) => setMsg({ text, bad: true })).current;
	const here = location.pathname === '/account' ? '/' : location.pathname + location.search;

	// a form's answer, back in the box
	async function sent(e: FormEvent<HTMLFormElement>, handler: string) {
		e.preventDefault();
		const form = e.currentTarget, data = new FormData(form, (e.nativeEvent as SubmitEvent).submitter);
		setBusy(true); setMsg({ text: '', bad: false });
		let a: Answer | null = null;
		try {
			const r = await fetch(`/account?/${handler}`, { method: 'POST', body: data, headers: { accept: 'application/json' } });
			a = await r.json();
		} catch { a = null; }
		setBusy(false);
		if (!a) { setCheck((c) => c + 1); setMsg({ text: 'Something went wrong. Try again in a moment.', bad: true }); return; }
		if (a.type === 'redirect') { location.href = a.location; return; } // on to Google, or to Stripe
		if (a.type === 'failure') { setCheck((c) => c + 1); setMsg({ text: a.data.message || 'Something went wrong. Try again in a moment.', bad: true }); return; }
		const done = a.data.done;
		if (done === 'note') { setNote(a.data.note || ''); setAsked('note'); return; }
		if (done === 'newpass') { setAsked('account'); setMsg({ text: 'Your password has been changed.', bad: false }); return; }
		if (done === 'erased') {
			setWho(null); setAsked('signin'); setMsg({ text: 'Your account has been deleted.', bad: false });
			// the menu's button is Sign in again; the page under it is redrawn signed out once the box closes
			const label = document.getElementById('account-label');
			if (label) label.textContent = 'Sign in';
			document.querySelector('.account-btn')?.classList.remove('is-profile');
			return;
		}
		// who is signed in has changed: the page is drawn again, as them
		onclose();
		location.reload();
	}

	const field = (name: string, label: string, type: string, autocomplete: string, min?: number) =>
		<label>{label}<input type={type} name={name} className="table-search" autoComplete={autocomplete} required minLength={min} /></label>;
	const link = (to: View, label: string) => <button type="button" className="link-btn" onClick={() => go(to)}>{label}</button>;
	const google = (
		<>
			<form method="post" action="/account?/google" onSubmit={(e) => sent(e, 'google')}>
				<input type="hidden" name="back" value={here} />
				<button type="submit" className="google-btn" disabled={busy}>{GOOGLE}<span>Continue with Google</span></button>
			</form>
			<div className="account-or">or</div>
		</>
	);
	const bot = <BotCheck key={check} sitekey={botCheck} failed={failed} />;
	const form = (handler: string, children: ReactNode, cls = 'account-form') =>
		<form className={cls || undefined} method="post" action={`/account?/${handler}`} onSubmit={(e) => sent(e, handler)}>{children}</form>;

	let body: ReactNode = null;
	if (view === 'signin') body = <>
		{google}
		{form('signin', <>{field('email', 'Email', 'email', 'username')}{field('password', 'Password', 'password', 'current-password')}{bot}<button type="submit" className="mt-btn" disabled={busy}>Sign in</button></>)}
		<div className="account-links">{link('signup', 'Create an account')}{link('reset', 'Forgotten your password?')}</div>
	</>;
	else if (view === 'signup') body = <>
		{google}
		{form('signup', <>{field('email', 'Email', 'email', 'email')}{field('password', 'Password (8 characters or more)', 'password', 'new-password', 8)}{bot}<button type="submit" className="mt-btn" disabled={busy}>Create account</button></>)}
		<div className="stats-note">By creating an account you agree to the <a href="/terms">terms of use</a> and the <a href="/privacy">privacy notice</a>.</div>
		<div className="account-links">{link('signin', 'Already have an account? Sign in')}</div>
	</>;
	else if (view === 'reset') body = <>
		<p className="account-text">Enter your email and we'll send you a link to choose a new password.</p>
		{form('reset', <>{field('email', 'Email', 'email', 'username')}{bot}<button type="submit" className="mt-btn" disabled={busy}>Send the link</button></>)}
		<div className="account-links">{link('signin', 'Back to sign in')}</div>
	</>;
	else if (view === 'newpass') body = form('newpass', <>{field('password', 'New password (8 characters or more)', 'password', 'new-password', 8)}<button type="submit" className="mt-btn" disabled={busy}>Save password</button></>);
	else if (view === 'note') body = <><p className="account-text">{note}</p><div className="account-links">{link('signin', 'Back to sign in')}</div></>;
	else if (view === 'subscribe') body = <>
		<p className="account-text">Free for everyone: the model's win, draw and loss chances for every match in the next 7 days, results and the model's record, the club ratings, league tables and the betting comparison pages.</p>
		<p className="account-text">For subscribers: the chances for matches further ahead, the projected score, the key reasons and full model detail behind every prediction, predicted line-ups, every league's projected table with each club's finishing chances, and the full player ranks (the top 50 overall, the top 10 in each league and the top 10 in each position are free).</p>
		{!pay ? <p className="account-text"><b>Subscriptions are coming soon.</b> Until then, everything listed as free above is here for everyone, with no account needed.</p>
			: sub?.subscriber ? <p className="account-text"><b>This account is subscribed.</b></p>
			: who ? <>
				<p className="account-text">Cancel whenever you like: the subscription then runs to the end of the time paid for. Payment is taken by Stripe; this site never sees your card. See the <a href="/terms">terms</a>.</p>
				{form('subscribe', <><button type="submit" name="plan" value="monthly" className="mt-btn account-out" disabled={busy}>Subscribe · {prices.monthly}</button>
					<button type="submit" name="plan" value="yearly" className="mt-btn account-out" disabled={busy}>Subscribe · {prices.yearly}</button></>, 'account-plans')}
			</>
			: <p className="account-text"><b>{prices.monthly}, or {prices.yearly}.</b> Sign in or create a free account first, then subscribe from here.</p>}
		<div className="account-links">{link(who ? 'account' : 'signin', who ? 'Back to your account' : 'Sign in')}</div>
	</>;
	else if (view === 'account' && who) body = <>
		<p className="account-text">Signed in as <b>{who.email}</b></p>
		{sub?.paywall && (sub.subscriber
			? <>
				<p className="account-text">Subscription: <b>{sub.status ? (sub.status === 'past_due' ? 'payment due' : sub.status) : 'active'}</b>{sub.plan ? ` (${sub.plan})` : ''}{sub.renewsAt ? ` · ${sub.ends ? 'ends' : 'renews'} ${longDate(sub.renewsAt.slice(0, 10))}` : ''}</p>
				{pay && sub.status && form('manage', <button type="submit" className="mt-btn account-out" disabled={busy}>Manage or cancel subscription</button>, '')}
			</>
			: <p className="account-text">No subscription on this account. {link('subscribe', 'What subscribers get')}</p>)}
		{form('signout', <button type="submit" className="mt-btn account-out" disabled={busy}>Sign out</button>, '')}
		<div className="account-links">{link('delete', 'Delete account')}</div>
	</>;
	else if (view === 'delete' && who) body = <>
		<p className="account-text">This deletes your account (<b>{who.email}</b>) and its sign-in details for good. It can't be undone.</p>
		{form('erase', <button type="submit" className="mt-btn account-out account-danger" disabled={busy}>Delete my account</button>, '')}
		<div className="account-links">{link('account', 'Keep my account')}</div>
	</>;
	return <>{body}<div className={`stats-note${msg.bad ? ' bad' : ''}`} id="account-msg" role={msg.bad ? 'alert' : 'status'}>{msg.text}</div></>;
}

// The box over the page: its title, a close button, and the box. Closing it (the button, Escape, a
// click outside it) puts the focus back on the menu's button.
function AccountModal(props: AccountProps & { start: View | null; onclose: () => void }) {
	const [title, setTitle] = useState(TITLES[props.start || 'signin']);
	useEffect(() => {
		const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') props.onclose(); };
		addEventListener('keydown', esc);
		return () => removeEventListener('keydown', esc);
	}, [props]);
	return (
		<div className="modal-overlay" id="account-modal" onClick={(e) => { if (e.target === e.currentTarget) props.onclose(); }}>
			<div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="account-title">
				<div className="modal-header">
					<div id="account-title">{title}</div>
					<button type="button" className="modal-close" aria-label="Close" onClick={props.onclose}>&times;</button>
				</div>
				<div id="account-body"><AccountBox {...props} onview={setTitle} /></div>
			</div>
		</div>
	);
}

// Opened by the menu's button (Sign in or Profile) and by any link to a view of the account page
// ("What subscribers get"); a click with a key held opens the page as usual, and on the account page
// itself the links do what they say
export function accountBox(holder: HTMLElement, props: AccountProps) {
	const root = createRoot(holder);
	const button = document.querySelector<HTMLElement>('.account-btn');
	const close = () => { root.render(null); button?.focus(); };
	const open = (start: View | null) => {
		// (the menu closes first, on a phone)
		if (document.body.classList.contains('menu-open')) document.querySelector<HTMLElement>('.menu-btn')?.click();
		root.render(<AccountModal {...props} start={start} onclose={close} key={Date.now()} />);
	};
	document.addEventListener('click', (e) => {
		const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a.account-btn, a[href^="/account?view="]');
		if (!a || location.pathname === '/account' || e.metaKey || e.ctrlKey || e.shiftKey) return;
		e.preventDefault();
		const view = new URL(a.href).searchParams.get('view');
		open(view && view in TITLES ? (view as View) : null);
	});
}
