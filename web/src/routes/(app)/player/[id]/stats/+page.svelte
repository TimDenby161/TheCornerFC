<script lang="ts">
	import { page } from '$app/state';
	import Crest from '#lib/components/Crest.svelte';

	let { data } = $props();
	// this tab with a season and totals or per 90 picked; the latest season and totals are left out
	const address = (year: number | undefined, per90: boolean | undefined) => {
		const q = new URLSearchParams({ ...(data.any && year !== data.latest ? { s: String(year) } : {}), ...(per90 ? { per90: '1' } : {}) }).toString();
		return q ? `?${q}` : page.url.pathname;
	};
</script>

<svelte:head>
	<title>{data.name} stats · The Corner FC</title>
	<meta name="description" content="{data.name}'s league appearances, minutes, goals, assists and cards, season by season." />
</svelte:head>

{#snippet tile(label: string, value: string | number | null, sub = '')}
	<div class="team-stat"><div class="team-stat-label">{label}</div><div class="team-stat-value">{value ?? '–'}</div>{#if sub}<div class="team-stat-sub">{sub}</div>{/if}</div>
{/snippet}

{#if !data.any}
	<div class="empty-state">No season stats for him yet.</div>
{:else}
	<div class="stats-controls">
		<div class="chip-scroll">
			{#each data.years as y (y.y)}
				<a role="button" class="filter-chip" href={address(y.y, data.per90)} aria-pressed={y.y === data.year} data-sveltekit-reset="false">{y.label}</a>
			{/each}
		</div>
		<div class="seg">
			<a role="button" class="seg-link" href={address(data.year, false)} aria-pressed={!data.per90} data-sveltekit-reset="false">Totals</a>
			<a role="button" class="seg-link" href={address(data.year, true)} aria-pressed={data.per90} data-sveltekit-reset="false">Per 90</a>
		</div>
	</div>
	<div class="season-clubs">
		{#each data.clubs as c (c.team)}
			<div class="season-club"><Crest id={c.team} name={c.name} href="/club/{c.team}" />
				<a class="team-link" href="/club/{c.team}">{c.name}</a><span class="dim"> · {c.comp} · {c.apps} apps · {c.minutes.toLocaleString('en-GB')}′</span></div>
		{/each}
	</div>
	<div class="team-stats compact">
		{@render tile('Apps', data.apps, data.started != null ? `${data.started} started` : '')}
		{@render tile('Minutes', data.minutes.toLocaleString('en-GB'))}
		{@render tile('Goals', data.goals)}
		{@render tile('Assists', data.assists)}
		{@render tile('Yellow cards', data.yellow)}
		{@render tile('Red cards', data.red)}
	</div>
	<div class="page-note">League matches only{data.per90 ? `, per 90 minutes (${data.minutes.toLocaleString('en-GB')} minutes)` : ''}.{data.partial ? ' Leagues without match-by-match data give season totals only, so starts are missing there.' : ''}</div>
{/if}
