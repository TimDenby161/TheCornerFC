<script lang="ts">
	import { page } from '$app/state';
	import '#lib/placed.css';
	import PersonChip from '#lib/components/PersonChip.svelte';

	let { data, children } = $props();
	const TABS = [['', 'Overview'], ['xi', 'Predicted XI'], ['formations', 'Formations'], ['players', 'Players']];
	const base = $derived(`/nation/${encodeURIComponent(data.name)}`);
	const tab = $derived(decodeURIComponent(page.url.pathname).slice(`/nation/${data.name}`.length + 1).split('/')[0]);
</script>

<section class="panel" data-tab="club" data-active="true">
	<div id="club-body">
		<div class="pl-hero">
			{#if data.flag}<img class="country-flag-lg" src="https://flagcdn.com/w160/{data.flag}.png" alt="" />{:else}<span></span>{/if}
			<div class="pl-hero-main">
				<h2>{data.name}</h2>
				{#if data.coach}<div class="pl-hero-club pl-hero-nat"><PersonChip name={data.coach} size="player-photo coach-photo" /><span class="pl-meta" title="Head coach">{data.coach}</span></div>{/if}
			</div>
			{#if data.rating}
				<div class="pl-hero-rank rel-{data.rating.tier}" title="National team Elo rating: world #{data.rating.rank} of {data.rating.of}{data.rating.change != null ? ` · ${data.rating.change >= 0 ? '+' : ''}${data.rating.change} on a year ago` : ''}">
					<span class="val">{data.rating.current}</span><span class="lbl"></span></div>
			{/if}
		</div>
		<nav class="page-tabs" aria-label="{data.name}'s pages">
			{#each TABS as [key, label] (key)}
				<a href={key ? `${base}/${key}` : base} aria-current={tab === key ? 'page' : undefined} data-sveltekit-reset="false">{label}</a>
			{/each}
		</nav>
		<div id="nat-tab">{@render children()}</div>
	</div>
</section>
