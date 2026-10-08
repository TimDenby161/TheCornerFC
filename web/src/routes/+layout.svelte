<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { oldAddress } from '#lib/menu.ts';

	// Every page. The site's own pages add the menu and the account box round this ((app)); the
	// plain text pages (how the models work, terms, privacy) stand on their own ((text)).
	let { data, children } = $props();

	// A link shared from the old site (thecornerfc.com/#/club/42/matches, #/players?c=39&sort=age)
	// names its page after a #, which the server never sees: the page goes to the same address here.
	$effect(() => {
		const old = oldAddress(location.hash);
		if (old) goto(old, { replace: true });
	});
	// The server wrote this page's days and kick-off times in the time zone it had for this visitor.
	// Tell it the browser's own, and where that is a different one, ask for the page again.
	$effect(() => {
		const mine = Intl.DateTimeFormat().resolvedOptions().timeZone;
		if (!mine || mine === data.tz) return;
		document.cookie = `tz=${encodeURIComponent(mine)}; path=/; max-age=31536000; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
		invalidateAll();
	});
</script>

{@render children()}

<style>
	/* the app's own wrapper takes no part in the layout (a rule here, not a style attribute: the
	   security policy allows no inline styles) */
	:global(#app) { display: contents; }
	/* (and should a new version of the framework word that hidden line's style differently, so the
	   policy stops it, it stays out of sight) */
	:global(#svelte-announcer) { position: absolute; left: 0; top: 0; clip-path: inset(50%); overflow: hidden; white-space: nowrap; width: 1px; height: 1px; }
</style>
