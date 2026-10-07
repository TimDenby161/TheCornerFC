<script lang="ts">
	import '../../../docs/assets/styles.css';
	import '#lib/crest-hues.css';
	import '../app.css';
	import { page } from '$app/state';
	import { MENU, sectionHref, tabFor } from '#lib/menu.ts';

	let { children } = $props();
	let menuOpen = $state(false);
	let theme = $state('');

	const tab = $derived(tabFor(page.url.pathname));
	const current = $derived(MENU.flatMap((g) => g.sections).find((s) => s.path && page.url.pathname.startsWith(s.path)));

	// The server writes <body data-tab>; after a move between pages in the browser it follows here.
	$effect(() => { document.body.dataset.tab = tab; });
	$effect(() => { document.body.classList.toggle('menu-open', menuOpen); });
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
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') menuOpen = false; }} />

<a class="skip-link" href="#main">Skip to content</a>

<header>
	<div class="app-bar">
		<button type="button" class="menu-btn" aria-label="Menu" aria-expanded={menuOpen} aria-controls="main-menu" onclick={() => (menuOpen = !menuOpen)}>&#9776;</button>
		<a class="brand" href="/" aria-current={tab === 'home' ? 'page' : undefined}><span class="brand-mark" aria-hidden="true"></span><span>The Corner FC</span></a>
		<h1 class="app-title">{current?.label ?? 'Home'}</h1>
	</div>
	<nav class="tabs" id="main-menu" aria-label="Main">
		<div class="menu-links">
			{#each MENU as group (group.label)}
				<p class="nav-label">{group.label}</p>
				{#each group.sections as s (s.label)}
					<a class="menu-link" href={sectionHref(s)} aria-current={s === current ? 'page' : undefined} onclick={() => (menuOpen = false)}>{s.label}</a>
				{/each}
			{/each}
			<!-- Room kept for an advert. Empty and out of the layout until adverts are switched on -->
			<div class="ad-slot ad-rail" id="ad-rail" aria-hidden="true"></div>
		</div>
		<div class="menu-foot">
			<div class="theme-pick seg" role="group" aria-label="Theme">
				{#each [['', 'Device'], ['light', 'Light'], ['dark', 'Dark']] as [value, label] (value)}
					<button type="button" aria-pressed={theme === value} onclick={() => setTheme(value)}>{label}</button>
				{/each}
			</div>
		</div>
	</nav>
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="menu-backdrop" hidden={!menuOpen} onclick={() => (menuOpen = false)}></div>
</header>

<main id="main" tabindex="-1" inert={menuOpen}>
	<div class="ad-slot ad-top" id="ad-top" aria-hidden="true"></div>
	{@render children()}
</main>
