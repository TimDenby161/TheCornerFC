<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { SITE_ENV } from '#lib/config.ts';
	import { oldAddress } from '#lib/menu.ts';
	import { keepZone } from '#lib/timeChoice.ts';

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
	// Tell it the browser's own, and where that is a different one, ask for the page again. Not
	// for a visitor who chose UK time in the menu: their zone is never kept.
	$effect(() => {
		const mine = Intl.DateTimeFormat().resolvedOptions().timeZone;
		if (data.ukTime || !mine || mine === data.tz) return;
		keepZone(mine);
		invalidateAll();
	});
</script>

{#if SITE_ENV !== 'production'}<p id="staging-strip">Staging: test data, not the live site</p>{/if}
{@render children()}

<style>
	/* the app's own wrapper takes no part in the layout (a rule here, not a style attribute: the
	   security policy allows no inline styles) */
	:global(#app) { display: contents; }
	/* staging only: a strip that can't be missed, clear of the menu and of the advert spaces */
	#staging-strip { position: fixed; left: 0; bottom: 0; z-index: 1000; margin: 0; padding: 4px 12px; background: #b00020; color: #fff; font: 700 12px/1.4 system-ui, sans-serif; letter-spacing: 0.04em; text-transform: uppercase; pointer-events: none; }
	/* (and should a new version of the framework word that hidden line's style differently, so the
	   policy stops it, it stays out of sight) */
	:global(#svelte-announcer) { position: absolute; left: 0; top: 0; clip-path: inset(50%); overflow: hidden; white-space: nowrap; width: 1px; height: 1px; }
</style>
