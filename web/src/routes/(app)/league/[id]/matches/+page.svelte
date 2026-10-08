<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import Crest from '#lib/components/Crest.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';

	let { data } = $props();
	// this tab on another round (the round it opens on is left out of the address)
	const address = (round: string | null) => (round == null ? page.url.pathname : `?${new URLSearchParams({ round })}`);
</script>

<svelte:head>
	<title>{data.label} matches · The Corner FC</title>
	<meta name="description" content="{data.label} fixtures and results round by round, with the model's chances for the matches to come." />
</svelte:head>

{#if !data.any}
	<div class="empty-state">No fixtures yet this season.</div>
{:else}
	<div class="round-nav">
		{#if data.prev != null}<a role="button" class="filter-chip" href={address(data.prev)} aria-label="Previous round" data-sveltekit-reset="false">‹</a>{:else}<button type="button" class="filter-chip" disabled aria-label="Previous round">‹</button>{/if}
		<select id="round-select" aria-label="Round" value={data.round} onchange={(e) => goto(address(e.currentTarget.value), { reset: false })}>
			{#each data.rounds as r (r.key)}<option value={r.key}>{r.label}</option>{/each}
		</select>
		{#if data.next != null}<a role="button" class="filter-chip" href={address(data.next)} aria-label="Next round" data-sveltekit-reset="false">›</a>{:else}<button type="button" class="filter-chip" disabled aria-label="Next round">›</button>{/if}
	</div>
	{#each data.days as day (day.name)}
		<div class="modal-section">{day.name}</div>
		{#each day.matches as f (f.id)}
			<div class="lf-row">
				<div class="lf-team lf-home" class:lf-win={f.home.won}><a class="team-link" href="/club/{f.home.id}">{f.home.name}</a><Crest id={f.home.id} name={f.home.name} href="/club/{f.home.id}" /></div>
				<div class="lf-mid" class:lf-live={f.live}>{#if f.score}<b>{f.score}</b>{#if f.pens}<span class="lf-note">{f.pens}</span>{/if}{:else if f.off}<span class="lf-note">{f.off}</span>{:else}<LocalTime iso={f.kickoff} show="time" />{/if}</div>
				<div class="lf-team" class:lf-win={f.away.won}><Crest id={f.away.id} name={f.away.name} href="/club/{f.away.id}" /><a class="team-link" href="/club/{f.away.id}">{f.away.name}</a></div>
				{#if f.xg}<div class="lf-sub" title="The model's expected goals for each side">{f.xg}</div>{/if}
				{#if f.probs}<div class="lf-sub">{f.probs}</div>{/if}
			</div>
		{/each}
	{/each}
{/if}
