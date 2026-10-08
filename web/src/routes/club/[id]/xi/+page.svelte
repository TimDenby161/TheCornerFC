<script lang="ts">
	import NextMatchCard from '#lib/components/NextMatchCard.svelte';
	import Pitch from '#lib/components/Pitch.svelte';
	import { rankTier } from '#lib/club.ts';

	let { data } = $props();
	// start chance colour: 80%+ green, 60-80 yellow, 40-60 orange, under 40 red
	const startTier = (c: number) => (c >= 80 ? 4 : c >= 60 ? 3 : c >= 40 ? 2 : 1);
</script>

<svelte:head>
	<title>{data.name} predicted XI · The Corner FC</title>
	<meta name="description" content="The line-up the model expects {data.name} to start in their next match." />
</svelte:head>

{#snippet tile(label: string, v: number | null, tip: string)}
	{#if v != null}<div class="sq-tile" title={tip}><span class="sq-lbl">{label}</span><span class="rel-chip rel-{rankTier(v)}">{Math.round(v)}</span></div>{/if}
{/snippet}

{#if data.paywall}
	<div class="empty-state">Predicted line-ups are for subscribers.</div>
{:else if !data.spots}
	<div class="empty-state">No predicted XI for this club (it needs player data from its recent matches).</div>
{:else}
	{#snippet pitch()}
		<div class="club-section pp-section">
			<Pitch kind="pp-pitch" kit={data.kit}>
				{#each data.spots! as s (s.id)}
					<a class="pp-spot xi-spot sq-{startTier(s.chance)} sx-{s.x} sy-{s.y}" href="/player/{s.id}" title={s.tip}>
						<span class="pp-rank rk-{rankTier(s.rank ?? 0)}">{s.rank == null ? '–' : Math.round(s.rank)}</span><span class="pp-name">{s.name}</span>
						<span class="pp-meta"><span class="sc-{startTier(s.chance)}">{s.chance}%</span> · {s.mins}′</span></a>
				{/each}
			</Pitch>
			{#if data.average != null}<div class="page-note u-center">Average rank {data.average}</div>{/if}
		</div>
	{/snippet}
	{#if data.next || data.squad}
		<div class="ov-top">
			<div class="ov-side">
				{#if data.next}<NextMatchCard n={data.next} />{/if}
				{#if data.squad}
					<div class="next-card squad-card">
						<div class="next-top"><span class="next-label">Squad</span></div>
						<div class="sq-tiles">
							{@render tile('Attack', data.squad.attack, "Expected players' ratings, weighted by expected minutes and how much each position attacks")}
							{@render tile('Defence', data.squad.defence, "Expected players' ratings, weighted by expected minutes and how much each position defends")}
							{@render tile('Strength', data.squad.strength, "Every expected player's rating, weighted by expected minutes (bench minutes included)")}
						</div>
					</div>
				{/if}
			</div>
			{@render pitch()}
		</div>
	{:else}
		{@render pitch()}
	{/if}
{/if}
