<script lang="ts">
	import { page } from '$app/state';
	import '#lib/placed.css';
	import { currentInView } from '#lib/actions.ts';
	import Crest from '#lib/components/Crest.svelte';
	import { pageHref } from '#lib/menu.ts';

	let { data, children } = $props();
	const base = $derived(`/league/${data.id}`);
	const tab = $derived(page.url.pathname.slice(base.length + 1).split('/')[0]);
</script>

<section class="panel" data-tab="club" data-active="true">
	<div id="club-body">
		<div class="pl-hero">
			<Crest id={data.id} name={data.name} league size="club-logo-lg" />
			<div class="pl-hero-main">
				<h2>{data.name}</h2>
				<div class="pl-hero-club">{#if data.flag}<img class="flag" src="https://flagcdn.com/w40/{data.flag}.png" alt="" loading="lazy" />{/if}<span><a class="nat-link" href={pageHref('country', data.countryKey)}>{data.country}</a></span></div>
			</div>
			{#if data.avg}
				<div class="pl-hero-rank rel-{data.avg.tier}" title="Average Baseline Strength (long-term Elo) of the clubs playing in this league">
					<span class="val">{data.avg.value}</span><span class="lbl">Avg baseline</span></div>
			{/if}
		</div>
		{#if data.hasData}
			<nav class="page-tabs" aria-label="{data.name}'s pages" use:currentInView={page.url.pathname}>
				{#each data.tabs as [key, label] (key)}
					<a href="{base}/{key}" aria-current={tab === key ? 'page' : undefined} data-sveltekit-reset="false">{label}</a>
				{/each}
			</nav>
			<div id="league-tab">{@render children()}</div>
		{:else}
			<div class="empty-state">No data for this competition this season.</div>
		{/if}
	</div>
</section>
