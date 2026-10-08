<script lang="ts">
	import MatchCard from '#lib/components/MatchCard.svelte';
	import MatchHead from '#lib/components/MatchHead.svelte';

	let { data } = $props();
	const move = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
	const lines = (l: (number | null)[]) => ['GK', 'DEF', 'MID', 'FWD'].map((k, i) => `${k} ${l[i] == null ? '–' : Math.round(l[i]!)}`).join(' · ');
</script>

<svelte:head>
	<title>{data.name} {data.view === 'results' ? 'results' : 'fixtures'} · The Corner FC</title>
	<meta name="description" content="{data.name}'s upcoming fixtures with the model's win chance, and every result since 2020 with the rating after it." />
</svelte:head>

{#if !data.fixtureCount && !data.resultCount}
	<div class="empty-state">No matches for this club yet.</div>
{:else}
	<div class="stats-controls u-mt0">
		<form class="seg" method="get" data-sveltekit-reset="false">
			<button type="submit" aria-pressed={data.view === 'fixtures'}>Fixtures{data.fixtureCount ? ` (${data.fixtureCount})` : ''}</button>
			<button type="submit" name="view" value="results" aria-pressed={data.view === 'results'}>Results{data.resultCount ? ` (${data.resultCount})` : ''}</button>
		</form>
	</div>
	{#if data.view === 'fixtures'}
		{#if data.fixtures.length}
			<div class="card-list">
				{#each data.fixtures as f (f.card.id)}
					<MatchCard m={f.card} when="day" lineups={false}>
						{#snippet extra()}<div class="club-card-extra"><span>{f.comp}</span>{#if f.win != null}<span><b>{f.win}%</b> win</span>{/if}</div>{/snippet}
					</MatchCard>
				{/each}
			</div>
			<div class="page-note">Projected score and win chance from the model.</div>
		{:else}
			<div class="empty-state">No upcoming fixtures for this club.</div>
		{/if}
	{:else if data.results.length}
		<div class="card-list" id="club-results">
			{#each data.results as r (r.key)}
				<div class="match-card club-res-{r.res}">
					<MatchHead home={r.home} away={r.away} status="FT" hg={r.hg} ag={r.ag} homeXg={r.homeXg} awayXg={r.awayXg}>
						{#snippet meta()}{r.meta}{/snippet}
					</MatchHead>
					{#if r.lines}<div class="market-line" title="Average player rank (0-100) by line">Starting XI {lines(r.lines)}</div>{/if}
					<div class="club-card-extra">
						<span title={r.attack != null && r.defence != null ? `Attack ${Math.round(r.attack)} · Defence ${Math.round(r.defence)} after the match` : undefined}>Elo <b>{r.rank.toFixed(1)}</b></span>
						<span class="rank-move">{#if r.move != null}<span class={r.move > 0 ? 'form-up' : r.move < 0 ? 'form-down' : ''}>{move(r.move)}</span>{/if}</span>
					</div>
				</div>
			{/each}
		</div>
		{#if !data.showAll && data.resultCount > data.results.length}
			<a class="show-all" href="?view=results&all=1" data-sveltekit-reset="false">Show all {data.resultCount.toLocaleString('en-GB')}</a>
		{/if}
		<div class="page-note">Elo: the club's Elo rating after the match; the change is how far that match moved it.</div>
	{:else}
		<div class="empty-state">No results for this club yet.</div>
	{/if}
{/if}
