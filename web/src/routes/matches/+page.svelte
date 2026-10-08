<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import FilterMenu from '#lib/components/FilterMenu.svelte';
	import MatchCard from '#lib/components/MatchCard.svelte';

	let { data } = $props();

	// this page with another day (or round: a round goes by its first day) and the same menu choice
	const address = (d: string | null) => {
		const q = new URLSearchParams({ ...(data.filter !== 'all' ? { c: data.filter } : {}), ...(d ? { d } : {}) }).toString();
		return q ? `?${q}` : page.url.pathname;
	};
	const picked = (e: Event) => { const d = (e.currentTarget as HTMLInputElement | HTMLSelectElement).value; if (d) goto(address(d), { reset: false }); };
	// a competition's (or a day's) matches fold away under its name; which are folded is the visitor's own
	let folded = $state<string[]>([]);
	const fold = (key: string) => (folded = folded.includes(key) ? folded.filter((k) => k !== key) : [...folded, key]);
	const byRound = $derived(data.mode === 'rounds');
</script>

<svelte:head>
	<title>{data.title ? `${data.title} matches` : 'Matches'} · The Corner FC</title>
	<meta name="description" content="The model's win, draw and loss chances for {data.title ? `${data.title} matches` : 'every match'}, with projected goals and the bookmakers' chances for comparison." />
</svelte:head>

<section class="panel" data-tab="matches" data-active="true">
	<div class="match-bar">
		<div id="match-side">
			<div class="side-stick"><FilterMenu id="match-filters" menu={data.menu} action="/matches" /></div>
		</div>
		<div class="secondary-filters">
			{#if data.prev}<a class="nav-btn" href={address(data.prev)} aria-label={byRound ? 'Previous round' : 'Previous day'} data-sveltekit-reset="false">&#8249;</a>
			{:else}<button type="button" class="nav-btn" disabled aria-label="Previous round">&#8249;</button>{/if}
			{#if data.mode === 'rounds'}
				<select class="date-input" aria-label="Round" value={data.day} onchange={picked}>
					{#each data.rounds as r (r.day)}<option value={r.day}>{r.label}</option>{/each}
				</select>
			{:else}
				<input type="date" class="date-input" aria-label="Match date" value={data.day} onchange={picked} />
			{/if}
			{#if data.next}<a class="nav-btn" href={address(data.next)} aria-label={byRound ? 'Next round' : 'Next day'} data-sveltekit-reset="false">&#8250;</a>
			{:else}<button type="button" class="nav-btn" disabled aria-label="Next round">&#8250;</button>{/if}
			<a class="nav-btn today-btn" href={address(null)} title={byRound ? 'The round on now or next up' : undefined} data-sveltekit-reset="false">{byRound ? 'Next' : 'Today'}</a>
		</div>
	</div>
	<div id="matches-list">
		{#each data.groups as g (g.key)}
			{@const closed = folded.includes(g.key)}
			<div class="comp-group" class:collapsed={closed}>
				<div class="comp-group-header" role="button" tabindex="0" aria-expanded={!closed} onclick={() => fold(g.key)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fold(g.key); } }}>
					<span class="comp-group-caret" aria-hidden="true">{closed ? '▸' : '▾'}</span>
					<span class="comp-group-name">{g.name}</span>
					<span class="comp-group-count">{g.cards.length}</span>
				</div>
				<div class="card-list">{#each g.cards as m (m.id)}<MatchCard {m} />{/each}</div>
			</div>
		{:else}
			{#if data.mode === 'days'}
				<div class="empty-state">No matches on {data.dayName}.{#if data.upcoming}<br /><br /><a class="filter-chip" href={address(data.upcoming.day)}>Next: {data.upcoming.name}</a>{/if}</div>
			{:else}
				<div class="empty-state">No matches in this competition yet.</div>
			{/if}
		{/each}
	</div>
</section>
