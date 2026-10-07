<script lang="ts">
	import type { Snippet } from 'svelte';
	import Crest from './Crest.svelte';
	import { FINISHED, LIVE } from '#lib/matches.ts';
	import { pageHref } from '#lib/menu.ts';

	// A match card's top: when (meta), both clubs with chip and rating, and the score, or the
	// projected goals and likely score before it is played.
	type Side = { id: number; name: string; rank: number | null };
	let { home, away, status, hg = null, ag = null, penH = null, penA = null, homeXg = null, awayXg = null, likely = null, source = null, meta, right }:
		{ home: Side; away: Side; status: string; hg?: number | null; ag?: number | null; penH?: number | null; penA?: number | null;
			homeXg?: number | null; awayXg?: number | null; likely?: string | null; source?: string | null; meta: Snippet; right?: Snippet } = $props();
	const finished = $derived(FINISHED.has(status) && hg != null);
	const played = $derived(finished || (LIVE.has(status) && hg != null));
	const rankTitle = $derived(finished ? 'Strength going into this match (Elo)' : 'Current Strength (Elo)');
</script>

{#snippet rank(v: number | null)}{#if v != null && Number.isFinite(v)}<span class="club-score" title={rankTitle}>{Math.round(v).toLocaleString('en-GB')}</span>{/if}{/snippet}
{#snippet side(s: Side)}<Crest id={s.id} name={s.name} href={pageHref('club', s.id)} /><a class="team-link" href={pageHref('club', s.id)}>{s.name}</a>{/snippet}

<div class="match-card-top">
	<span class="match-meta">{@render meta()}</span>
	<span class="card-top-right">{@render right?.()}</span>
</div>
<div class="match-teams">
	<div class="match-team">
		<div class="mt-name">{@render side(home)}</div>
		<div class="score-badges">{@render rank(home.rank)}</div>
	</div>
	<div class="match-score">
		{#if played}
			<div class="score-row"><span class="final-box">{hg}</span><span class="vs-text">–</span><span class="final-box">{ag}</span></div>
			{#if penH != null}<div class="score-sub">pens {penH}–{penA}</div>{/if}
			{#if homeXg != null && awayXg != null}<div class="score-sub" title={source === 'backfill' ? 'Projected score, reconstructed afterwards from pre-match data' : 'Projected score, before kickoff'}>{homeXg.toFixed(1)}–{awayXg.toFixed(1)}</div>{/if}
		{:else if homeXg == null || awayXg == null}
			<div class="score-row"><span class="vs-text">vs</span></div>
		{:else}
			<div class="score-row" title="Projected goals (the model's expected goals)"><span class="proj-box">{homeXg.toFixed(1)}</span><span class="vs-text">xG</span><span class="proj-box">{awayXg.toFixed(1)}</span></div>
			{#if likely}<div class="score-sub" title="The single most likely score; most matches end some other way">Likely {likely}</div>{/if}
		{/if}
	</div>
	<div class="match-team away">
		<div class="mt-name">{@render side(away)}</div>
		<div class="score-badges">{@render rank(away.rank)}</div>
	</div>
</div>
