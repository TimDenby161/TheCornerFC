<script lang="ts">
	import Crest from './Crest.svelte';
	import Move from './Move.svelte';
	import SortTh from './SortTh.svelte';
	import type { Sort } from '#lib/league.ts';
	import { pageHref } from '#lib/menu.ts';
	import type { RatingRow } from '#lib/server/league.ts';

	// The clubs table on league and country pages: Baseline rank, the club, its place in the
	// competition's table (or matches rated, where there is none), and its ratings. Headers sort
	// it; # stays each club's Baseline Strength rank.
	let { rows, sort, def, table }: { rows: RatingRow[]; sort: Sort; def: string; table: boolean } = $props();
</script>

<div class="table-scroll"><table class="leaderboard clubs">
	<thead><tr>
		<SortTh key="rank" {sort} {def} title="Baseline Strength rank">#</SortTh><th></th>
		<SortTh key="club" {sort} {def} title="Club name">Club</SortTh>
		{#if table}<SortTh key="pos" {sort} {def} title="Actual position in the competition's table" cls="num col-spare">Table</SortTh>
		{:else}<SortTh key="played" {sort} {def} title="Matches rated" cls="num col-spare">Pl</SortTh>{/if}
		<SortTh key="lt" {sort} {def} title="Baseline Strength: long-term Elo" cls="num"><span class="th-full">Baseline</span><span class="th-short">Base</span></SortTh>
		<SortTh key="trend" {sort} {def} title="Current minus Baseline" cls="num col-gap">Gap</SortTh>
		<SortTh key="current" {sort} {def} title="Current Strength: Elo now" cls="num">Current</SortTh>
		<SortTh key="form" {sort} {def} title="Elo change over the last 6 matches" cls="num col-recent">Last 6</SortTh>
	</tr></thead>
	<tbody>
		{#each rows as r (r.team)}
			<tr>
				<td>{r.i}</td>
				<td><Crest id={r.team} name={r.name} href="/club/{r.team}" /></td>
				<td><a class="team-link" href="/club/{r.team}">{r.name}</a>{#if r.meta}{' '}<span class="club-meta"><a class="nat-link" href={pageHref('league', r.meta.league)}>{r.meta.name}</a></span>{/if}</td>
				<td class="num col-spare u-muted">{table ? (r.pos ?? '') : r.played}</td>
				<td class="num"><span class="rel-chip rel-{r.ltTier}">{Math.round(r.lt)}</span></td>
				<td class="num col-gap"><Move value={r.trend} /></td>
				<td class="num"><span class="rel-chip rel-{r.currentTier}">{Math.round(r.current)}</span></td>
				<td class="num col-recent"><Move value={r.form == null ? null : Math.round(r.form)} /></td>
			</tr>
		{/each}
	</tbody>
</table></div>
