<script lang="ts">
	import '../../styles/styles.css';
	import '#lib/crest-hues.css';
	import '../../app.css';
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { accountBox, openAccount } from '#lib/account.svelte.ts';
	import AccountBox from '#lib/components/AccountBox.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { ADS } from '#lib/config.ts';
	import { MENU, OWNER_MENU, methodologyHref, sectionHref, tabFor } from '#lib/menu.ts';
	import { owner } from '#lib/owner.svelte.ts';
	import { browserZone, keepUkTime, keepZone } from '#lib/timeChoice.ts';

	let { data, children } = $props();

	// The account box, opened by the button at the foot of the menu: Sign in, or the signed-in
	// visitor's profile under their initial. Closing it puts the focus back on that button.
	let accountTitle = $state('Sign in');
	let accountBtn = $state<HTMLElement>();
	const closeAccount = () => { if (accountBox.open) { accountBox.open = false; accountBtn?.focus(); } };
	let menuOpen = $state(false);
	let theme = $state('');

	const tab = $derived(tabFor(page.url.pathname));
	// the page's name, a line on what it shows and what its figures mean, where the page gives one
	type TabHead = { title: string; intro: string; more: string; key: [string, string][] };
	const head = $derived(page.data.tabHead as TabHead | undefined);
	// the Fantasy group: for the owner, known from an earlier visit or as soon as the database says so
	const menu = $derived((data.owner && owner.status !== 'no') || owner.status === 'ok' ? [...MENU, OWNER_MENU] : MENU);
	const current = $derived([...MENU, OWNER_MENU].flatMap((g) => g.sections).find((s) => s.path && page.url.pathname.startsWith(s.path)));

	// The server writes <body data-tab>; after a move between pages in the browser it follows here.
	$effect(() => { document.body.dataset.tab = tab; });
	$effect(() => { document.body.classList.toggle('menu-open', menuOpen); });
	// the advert spaces open only when adverts are on and the visitor isn't a subscriber
	$effect(() => {
		const preview = page.url.searchParams.get('ads') === 'preview';
		document.body.classList.toggle('ads-on', preview || (ADS.on && !data.sub?.subscriber));
		document.body.classList.toggle('ads-preview', preview);
	});
	$effect(() => {
		try {
			const kept = localStorage.getItem('fc.theme');
			theme = kept === 'light' || kept === 'dark' ? kept : '';
		} catch { /* storage blocked: follow the device */ }
	});
	function setTheme(to: string) {
		theme = to;
		if (to) document.documentElement.dataset.theme = to;
		else delete document.documentElement.dataset.theme;
		try {
			if (to) localStorage.setItem('fc.theme', to);
			else localStorage.removeItem('fc.theme');
		} catch { /* storage blocked: the choice lasts for this visit */ }
	}
	// Days and kick-off times in the visitor's own time (their zone kept in a cookie) or in UK time
	// (no zone kept): the pages are asked for again, written the chosen way.
	function setTimes(uk: boolean) {
		if (uk === data.ukTime) return;
		if (uk) keepUkTime(); else keepZone(browserZone());
		invalidateAll();
	}
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') { menuOpen = false; closeAccount(); } }} />

<a class="skip-link" href="#main">Skip to content</a>

<header>
	<div class="app-bar">
		<button type="button" class="menu-btn" aria-label="Menu" aria-expanded={menuOpen} aria-controls="main-menu" onclick={() => (menuOpen = !menuOpen)}>&#9776;</button>
		<a class="brand" href="/" aria-current={tab === 'home' ? 'page' : undefined}><span class="brand-mark" aria-hidden="true"></span><span>The Corner FC</span></a>
		<!-- the section's name; on a club's, player's, competition's or nation's page, its own -->
		<h1 class="app-title">{current?.label ?? (tab === 'club' && typeof page.data.name === 'string' ? page.data.name : 'Home')}</h1>
	</div>
	<nav class="tabs" id="main-menu" aria-label="Main">
		<div class="menu-links">
			{#each menu as group (group.label)}
				<p class="nav-label">{group.label}</p>
				{#each group.sections as s (s.label)}
					<a class="menu-link" href={sectionHref(s)} aria-current={s === current ? 'page' : undefined} onclick={() => (menuOpen = false)}>{s.label}</a>
				{/each}
			{/each}
			<!-- Room kept for an advert. Empty and out of the layout until adverts are switched on -->
			<div class="ad-slot ad-rail" id="ad-rail" aria-hidden="true"></div>
		</div>
		<div class="menu-foot">
			<!-- (a link, so it works before the page's script runs: then it opens the account page) -->
			<a class="account-btn" class:is-profile={!!data.user} href="/account" aria-haspopup="dialog" bind:this={accountBtn}
				onclick={(e) => { if (page.url.pathname === '/account' || e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); menuOpen = false; openAccount(); }}>
				<span class="account-mark" aria-hidden="true">{(data.user?.email || '').trim().charAt(0).toUpperCase()}</span><span id="account-label">{data.user ? 'Profile' : 'Sign in'}</span></a>
			<div class="theme-pick seg" role="group" aria-label="Theme">
				{#each [['', 'Device'], ['light', 'Light'], ['dark', 'Dark']] as [value, label] (value)}
					<button type="button" aria-pressed={theme === value} onclick={() => setTheme(value)}>{label}</button>
				{/each}
			</div>
			<div class="theme-pick time-pick seg" role="group" aria-label="Kick-off times">
				{#each [[false, 'My time'], [true, 'UK time']] as const as [uk, label] (label)}
					<button type="button" aria-pressed={data.ukTime === uk} onclick={() => setTimes(uk)}>{label}</button>
				{/each}
			</div>
		</div>
	</nav>
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="menu-backdrop" hidden={!menuOpen} onclick={() => (menuOpen = false)}></div>
</header>

{#if accountBox.open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="modal-overlay" id="account-modal" onclick={(e) => { if (e.target === e.currentTarget) closeAccount(); }}>
		<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="account-title">
			<div class="modal-header">
				<div id="account-title">{accountTitle}</div>
				<button type="button" class="modal-close" aria-label="Close" onclick={closeAccount}>&times;</button>
			</div>
			<div id="account-body"><AccountBox user={data.user} sub={data.sub} start={accountBox.view} onview={(t) => (accountTitle = t)} onclose={closeAccount} /></div>
		</div>
	</div>
{/if}

<main id="main" tabindex="-1" inert={menuOpen}>
	{#if head}
		<div class="tab-head" id="tab-head">
			<p class="tab-title" id="tab-title" aria-hidden="true">{head.title}</p>
			<p class="tab-intro" id="tab-intro">{head.intro}{#if head.more}{' '}<a href={methodologyHref(head.more)} data-sveltekit-reload>How it works</a>{/if}</p>
			{#if head.key.length}
				<details class="tab-key" id="tab-key"><summary>What the numbers mean</summary>
					<dl id="tab-key-list">{#each head.key as [term, meaning] (term)}<dt>{term}</dt><dd>{meaning}</dd>{/each}</dl>
				</details>
			{/if}
		</div>
	{/if}
	<div class="ad-slot ad-top" id="ad-top" aria-hidden="true"></div>
	{@render children()}
	{#if data.fresh.items.length || data.fresh.model}
		<footer class="freshness" id="freshness">
			{#each data.fresh.items as [label, iso, tip] (label)}<span title={tip}>{label} <LocalTime {iso} show="short" /> <LocalTime {iso} show="time" /></span>{/each}
			{#if data.fresh.model}<span title="Latest registered match model version">Model {data.fresh.model.name}{data.fresh.model.code ? ` · ${data.fresh.model.code}` : ''}</span>{/if}
		</footer>
	{/if}
	<footer class="site-links"><a href="/methodology" data-sveltekit-reload>How the models work</a> · <a href="/privacy" data-sveltekit-reload>Privacy, corrections &amp; security</a> · <a href="/terms" data-sveltekit-reload>Terms of use</a></footer>
</main>
