<script lang="ts">
	import { fitTable } from '#lib/actions.ts';
	import Crest from '#lib/components/Crest.svelte';
	import Flag from '#lib/components/Flag.svelte';
	import Move from '#lib/components/Move.svelte';

	let { data } = $props();
	const COLS = [
		['clubs', 'Clubs', 'Rated clubs playing in the league this season.', ''],
		['lt', 'Baseline', "Average Baseline Strength (long-term Elo) of the league's clubs: the number on the league's page.", ''],
		['trend', 'Gap', "Average Current Strength minus average Baseline Strength. Green: the league's clubs are rated above their long-term level; red: below it.", 'col-gap'],
		['current', 'Current', "Average Current Strength (Elo now) of the league's clubs.", '']
	];
</script>

<svelte:head>
	<title>Leagues · The Corner FC</title>
	<meta name="description" content="{data.leagues.length} leagues ranked by the average strength of their clubs, on one scale." />
</svelte:head>

<section class="panel" data-tab="leagues" data-active="true">
	<div id="leagues-body" use:fitTable={false}>
		{#if data.leagues.length}
			<div class="table-scroll"><table class="leaderboard clubs">
				<thead><tr>
					<th title="Position in this list, in the current sort order.">#</th>
					<th><span class="th-club">League</span></th>
					<th title="League name and its country's flag. Click a league to open its page.">League</th>
					{#each COLS as [key, label, tip, cls] (key)}
						<th class="num sortable {cls}" class:active={data.sort === key} aria-sort={data.sort === key ? 'descending' : undefined} title="{tip} Click to sort.">
							<a href={key === 'lt' ? '/leagues' : `?sort=${key}`} data-sveltekit-reset="false">{#if key === 'lt'}<span class="th-full">Baseline</span><span class="th-short">Base</span>{:else}{label}{/if}</a></th>
					{/each}
				</tr></thead>
				<tbody>
					{#each data.leagues as c, i (c.lid)}
						<tr>
							<td>{i + 1}</td>
							<td><Crest id={c.lid} name={c.name} league href="/league/{c.lid}" /></td>
							<td><div class="club-cell"><a class="team-link" href="/league/{c.lid}">{c.name}</a>
								{#if c.hasFlag}<span class="club-meta"><Flag key={c.countryKey} name={c.country} /></span>{/if}</div></td>
							<td class="num u-muted">{c.clubs}</td>
							<td class="num"><span class="rel-chip rel-{c.ltTier}">{c.lt}</span></td>
							<td class="num col-gap"><Move value={c.trend} /></td>
							<td class="num"><span class="rel-chip rel-{c.currentTier}">{c.current}</span></td>
						</tr>
					{/each}
				</tbody>
			</table></div>
			<div class="page-note">Averages over the clubs playing in each league this season.</div>
		{:else}
			<div class="empty-state">No leagues yet.</div>
		{/if}
	</div>
</section>
