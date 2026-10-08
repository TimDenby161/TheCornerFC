<script lang="ts" module>
	// The check that a visitor isn't a bot, on the sign-in, sign-up and reset forms (Cloudflare
	// Turnstile). Supabase verifies its answer before it acts. Cloudflare's script is asked for
	// only when a form that needs it is first shown.
	const SITE_KEY = '0x4AAAAAAFQgIiqxiuE9dqIM';
	const LIB = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
	type Turnstile = { render: (el: HTMLElement, o: Record<string, unknown>) => string; remove: (id: string) => void };
	let lib: Promise<Turnstile> | undefined;
	const load = () => (lib ||= new Promise<Turnstile>((resolve, reject) => {
		const s = document.createElement('script');
		s.src = LIB;
		s.onload = () => resolve((window as unknown as { turnstile: Turnstile }).turnstile);
		s.onerror = () => { lib = undefined; s.remove(); reject(new Error('bot-check')); };
		document.head.append(s);
	}));
</script>

<script lang="ts">
	// The widget writes its answer into the form it sits in (a field named cf-turnstile-response).
	// An answer passes once: the form draws a fresh check after a failed try.
	let { failed }: { failed: (message: string) => void } = $props();
	function mount(box: HTMLElement) {
		let id: string | undefined, gone = false;
		load().then((turnstile) => { if (!gone) id = turnstile.render(box, { sitekey: SITE_KEY }); })
			.catch(() => failed("Couldn't load the check that you're not a bot. Check your connection, or try without a content blocker."));
		return { destroy() { gone = true; if (id != null) (window as unknown as { turnstile: Turnstile }).turnstile?.remove(id); } };
	}
</script>

<div id="account-botcheck" use:mount></div>
