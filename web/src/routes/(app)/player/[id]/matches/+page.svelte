<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import { rankTier } from '#lib/club.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.name} matches · The Corner FC</title>
	<meta name="description" content="{data.name}'s latest league appearances: minutes, position, goals and assists, and his rank going into each match." />
</svelte:head>

{#if !data.matches.length}
	<div class="empty-state">No match-by-match data for him (only the leagues with per-match player stats have it).</div>
{:else}
	<div class="match-list">
		{#each data.matches as m (m.key)}
			<div class="match-row">
				<div class="mr-date">{m.date}</div>
				<div class="mr-opp"><Crest id={m.opp} name={m.oppName} href="/club/{m.opp}" />
					<span>{m.home ? 'v' : '@'} <a class="team-link" href="/club/{m.opp}">{m.oppName}</a></span></div>
				<div class="mr-res res-{m.res}">{m.gf}–{m.ga}</div>
				<div class="mr-rank" title="His rank going into the match">{#if m.rank == null}–{:else}<span class="rel-chip rel-{rankTier(m.rank)}">{Math.round(m.rank)}</span>{/if}</div>
				<div class="mr-sub"><span>{m.bits.join(' · ')}{#if m.card}{m.bits.length ? ' · ' : ''}<span class="card" class:red={m.card === 'red'}></span>{/if}</span></div>
			</div>
		{/each}
	</div>
	<div class="page-note">His last {data.matches.length} league appearances. The number on the right is his rank going into the match.</div>
{/if}
