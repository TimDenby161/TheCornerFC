<script lang="ts">
	import { page } from '$app/state';
	import ClubRatingTable from '#lib/components/ClubRatingTable.svelte';
	import Crest from '#lib/components/Crest.svelte';

	let { data } = $props();
	type Card = (typeof data.leagues)[number];
	const allHref = $derived.by(() => { const q = new URLSearchParams(page.url.search); q.set('all', '1'); return `?${q}`; });
</script>

<svelte:head>
	<title>{data.name} · The Corner FC</title>
	<meta name="description" content="{data.name}: its leagues ranked by the strength of their clubs, its cups, and its clubs on one scale." />
</svelte:head>

{#snippet card(c: Card)}
	<a class="lg-card" href="/league/{c.lid}"><Crest id={c.lid} name={c.name} league />
		<span class="lg-main"><span class="lg-name">{c.name}</span>{#if c.sub}<span class="lg-sub">{c.sub}</span>{/if}</span>
		{#if c.avg}<span class="rel-chip rel-{c.avg.tier}" title="Average Baseline Strength of its clubs">{c.avg.value}</span>{/if}</a>
{/snippet}

<section class="panel" data-tab="club" data-active="true">
	<div id="club-body">
		<div class="pl-hero">
			{#if data.flag}<img class="country-flag-lg" src="https://flagcdn.com/w160/{data.flag}.png" alt="" />{:else}<span></span>{/if}
			<div class="pl-hero-main">
				<h2>{data.name}</h2>
				<div class="pl-hero-club"><span class="pl-meta">{data.counts}</span></div>
			</div>
			{#if data.avg}
				<div class="pl-hero-rank rel-{data.avg.tier}" title="Average Baseline Strength (long-term Elo) of the 15 best clubs in its leagues">
					<span class="val">{data.avg.value}</span><span class="lbl">Top 15 clubs</span></div>
			{/if}
		</div>
		{#if data.leagues.length}
			<div class="modal-section u-mt0">Leagues</div><div class="lg-list">{#each data.leagues as c (c.lid)}{@render card(c)}{/each}</div>
			{#if data.leagues.length > 1}<div class="page-note">Strongest first, by the average Baseline Strength of their clubs.</div>{/if}
		{/if}
		{#if data.cups.length}
			<div class="club-section" class:u-mt0={!data.leagues.length}><div class="modal-section">{data.leagues.length ? 'Cups' : 'Competitions'}</div>
				<div class="lg-list">{#each data.cups as c (c.lid)}{@render card(c)}{/each}</div></div>
		{/if}
		{#if data.total}
			<div class="club-section"><div class="modal-section">Clubs</div>
				<div id="country-clubs"><ClubRatingTable rows={data.rows} sort={data.sort} def="current" table={false} /></div>
				{#if !data.showAll && data.total > data.rows.length}<a class="show-all" href={allHref} data-sveltekit-reset="false">Show all {data.total.toLocaleString('en-GB')}</a>{/if}</div>
		{/if}
	</div>
</section>
