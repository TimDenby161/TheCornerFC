<script lang="ts">
	import Pitch from './Pitch.svelte';
	import { rankTier } from '#lib/club.ts';
	import type { Spot } from '#lib/lineups.ts';
	import '#lib/placed.css';

	// An eleven on a pitch: keeper at the top, attacking down. Each spot is the player's rank over
	// his name, then his chance of starting and expected minutes (a predicted XI) or his position
	// (the XI that started). A started XI marked against the prediction is ringed green where he
	// was predicted and red where not, with the model's pick instead under a miss.
	let { spots, kit = null, ranks = true }: { spots: Spot[]; kit?: string[] | null; ranks?: boolean } = $props();
	// start chance colour: 80%+ green, 60-80 yellow, 40-60 orange, under 40 red
	const startTier = (c: number) => (c >= 80 ? 4 : c >= 60 ? 3 : c >= 40 ? 2 : 1);
	const cls = (s: Spot) => (s.predicted != null ? `xi-mark ${s.predicted ? 'xi-hit' : 'xi-miss'}` : `sq-${s.chance != null ? startTier(s.chance) : rankTier(s.rank ?? 0)}`);
</script>

<Pitch kind="pp-pitch" {kit}>
	{#each spots as s (s.id)}
		<a class="pp-spot xi-spot {cls(s)} sx-{s.x} sy-{s.y}" href="/player/{s.id}" title={s.tip}>
			{#if ranks}<span class="pp-rank rk-{rankTier(s.rank ?? 0)}">{s.rank == null ? '–' : Math.round(s.rank)}</span>{/if}<span class="pp-name">{s.name}</span>
			{#if s.chance != null || s.mins != null}
				<span class="pp-meta">{#if s.chance != null}<span class="sc-{startTier(s.chance)}">{s.chance}%</span>{/if}{s.chance != null && s.mins != null ? ' · ' : ''}{s.mins != null ? `${s.mins}′` : ''}</span>
			{:else}
				<span class="pp-meta">{s.label}</span>
			{/if}
			{#if s.instead}<span class="pp-instead"><span class="pp-instead-name">{s.instead.name}</span><span class="pp-instead-rank rk-{rankTier(s.instead.rank ?? 0)}">{s.instead.rank == null ? '–' : Math.round(s.instead.rank)}</span></span>{/if}
		</a>
	{/each}
</Pitch>
