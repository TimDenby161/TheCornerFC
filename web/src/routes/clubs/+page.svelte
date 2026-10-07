<script lang="ts">
	import { page } from '$app/state';
	import Crest from '#lib/components/Crest.svelte';
	import Move from '#lib/components/Move.svelte';
	import { ordinal } from '#lib/site.ts';
	import type { Sort } from '#lib/rankings.ts';

	let { data } = $props();

	const COLUMNS: { key: Sort; label: string; cls: string; tip: string }[] = [
		{ key: 'lt', label: 'Baseline', cls: '', tip: 'Baseline Strength: the long-term Elo rating, a smoothed rating weighted mostly to the average over the last 100 matches. Slow to move, and the better guide for matches months away.' },
		{ key: 'trend', label: 'Gap', cls: 'col-gap', tip: 'Gap: Current Strength minus Baseline Strength. Green: rated above its long-term level; red: below it.' },
		{ key: 'current', label: 'Current', cls: '', tip: 'Current Strength: the Elo rating after the latest match. 100 points is worth a goal a game.' },
		{ key: 'form', label: 'Last 6', cls: 'col-recent', tip: "Recent movement: how much the club's Elo rating has changed over its last 6 matches." }
	];

	// this page's address with some of its choices changed (a default is left out of the address)
	function href(change: Record<string, string | null>) {
		const q = new URLSearchParams(page.url.search);
		for (const [k, v] of Object.entries(change)) if (v === null) q.delete(k); else q.set(k, v);
		const s = q.toString();
		return s ? `?${s}` : page.url.pathname;
	}
	const title = $derived(data.leagueName ? `${data.leagueName} clubs` : 'Clubs');
</script>

<svelte:head>
	<title>{title} · The Corner FC</title>
	<meta name="description" content="Strength ratings for {data.total.toLocaleString('en-GB')} clubs{data.leagueName ? ` in the ${data.leagueName}` : ''} on one scale: long-term level, current rating and recent movement." />
</svelte:head>

<section class="panel" data-tab="table" data-active="true">
	<div id="table-wrap">
		{#if data.rows.length}
			<div class="table-scroll">
				<table class="leaderboard clubs">
					<thead>
						<tr>
							<th title="Position in this list, in the current sort order.">#</th>
							<th><span class="th-club">Club</span></th>
							<th title="Club name, with its country and league.">Club</th>
							<th class="num" title="World rank: place among every ranked club by Baseline Strength, whatever this list is filtered or sorted by.">World</th>
							<th class="num col-dom" title="In league: place by Baseline Strength among the clubs in its league this season.">In lg</th>
							{#each COLUMNS as col (col.key)}
								<th class="num sortable {col.cls}" class:active={data.sort === col.key} aria-sort={data.sort === col.key ? 'descending' : undefined} title={col.tip}>
									<a href={href({ sort: col.key === 'lt' ? null : col.key, page: null })} data-sveltekit-noscroll>{#if col.key === 'lt'}<span class="th-full">Baseline</span><span class="th-short">Base</span>{:else}{col.label}{/if}</a>
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each data.rows as r (r.team)}
							<tr>
								<td>{r.n}</td>
								<td><Crest id={r.team} name={r.name} /></td>
								<td>
									<div class="club-cell">
										<a class="team-link" href="/club/{r.team}">{r.name}</a>
										{#if data.league === null}
											<span class="club-meta"><span class="cm-league">{r.country} · <a class="nat-link" href={href({ c: String(r.league), page: null })}>{r.leagueName}</a></span></span>
										{/if}
									</div>
								</td>
								<td class="num">{r.place.world.toLocaleString('en-GB')}</td>
								<td class="num col-dom u-muted" title={r.place.dom ? `${ordinal(r.place.dom)} of ${r.place.domOf} in the ${r.leagueName} by Baseline Strength` : undefined}>{r.place.dom ?? ''}</td>
								<td class="num"><span class="rel-chip rel-{r.ltTier}">{r.lt}</span></td>
								<td class="num col-gap"><Move value={r.trend} /></td>
								<td class="num"><span class="rel-chip rel-{r.currentTier}">{r.current}</span></td>
								<td class="num col-recent"><Move value={r.form} /></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if data.pages > 1}
				<nav class="pager" aria-label="Pages">
					{#if data.pageNo > 1}<a class="mt-btn" href={href({ page: data.pageNo === 2 ? null : String(data.pageNo - 1) })}>Previous</a>{/if}
					<span>Page {data.pageNo} of {data.pages}</span>
					{#if data.pageNo < data.pages}<a class="mt-btn" href={href({ page: String(data.pageNo + 1) })}>Next</a>{/if}
				</nav>
			{/if}
		{:else}
			<div class="empty-state">No clubs found.</div>
		{/if}
	</div>
</section>

<style>
	.pager { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 16px 0; }
</style>
