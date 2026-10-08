<script lang="ts">
	import { page } from '$app/state';
	import { fitTable } from '#lib/actions.ts';
	import Move from '#lib/components/Move.svelte';

	let { data } = $props();
	const address = (o: { c?: string; sort?: string }) => {
		const c = o.c ?? data.confed, sort = o.sort ?? data.sort;
		const q = new URLSearchParams({ ...(c !== 'all' ? { c } : {}), ...(sort !== 'current' ? { sort } : {}) }).toString();
		return q ? `?${q}` : page.url.pathname;
	};
</script>

<svelte:head>
	<title>{data.confed === 'all' ? 'Nations' : `${data.confed} nations`} · The Corner FC</title>
	<meta name="description" content="National teams ranked by strength, from every men's international since 1872." />
</svelte:head>

<section class="panel" data-tab="nations" data-active="true">
	<div id="nations-body" use:fitTable={false}>
		<div class="filter-row u-mb10">
			<a role="button" class="filter-chip" href={address({ c: 'all' })} aria-pressed={data.confed === 'all'} data-sveltekit-reset="false">World</a>
			{#each data.confeds as c (c)}<a role="button" class="filter-chip" href={address({ c })} aria-pressed={data.confed === c} data-sveltekit-reset="false">{c}</a>{/each}
		</div>
		<div class="table-scroll"><table class="leaderboard clubs">
			<thead><tr>
				<th title="Position in this list, in the current sort order.">#</th>
				<th><span class="th-club">Nation</span></th>
				<th title="The national team and its confederation. Hover for its last 12 months and last match.">Nation</th>
				<th class="num sortable" class:active={data.sort === 'current'} aria-sort={data.sort === 'current' ? 'descending' : undefined} title="Current Strength: the Elo rating now. 100 points is about one goal a game on a neutral ground. Click to sort."><a href={address({ sort: 'current' })} data-sveltekit-reset="false">Current</a></th>
				<th class="num sortable" class:active={data.sort === 'change'} aria-sort={data.sort === 'change' ? 'descending' : undefined} title="Change in Current Strength over the last 12 months. Click to sort."><a href={address({ sort: 'change' })} data-sveltekit-reset="false">1 yr</a></th>
			</tr></thead>
			<tbody>
				{#each data.rows as n, i (n.name)}
					<tr title={n.tip}>
						<td>{i + 1}</td>
						<td>{#if n.flag}<img class="flag" src="https://flagcdn.com/w40/{n.flag}.png" alt="" loading="lazy" />{/if}</td>
						<td><div class="club-cell">{#if n.page}<a class="team-link" href="/nation/{encodeURIComponent(n.page)}">{n.name}</a>{:else}<span class="team-link">{n.name}</span>{/if}{#if n.confed}{' '}<span class="club-meta">{n.confed}</span>{/if}</div></td>
						<td class="num"><span class="rel-chip rel-{n.tier}">{n.current}</span></td>
						<td class="num"><Move value={n.change} /></td>
					</tr>
				{/each}
			</tbody>
		</table></div>
		<div class="page-note">Elo ratings from every men's full international since 1872 ({data.matches.toLocaleString('en-GB')} matches, the latest on {data.latest}), the club model's method with home advantage only away from neutral grounds. FIFA members that have played in the last four years. Results: <a href="https://github.com/martj42/international_results" rel="noopener">international_results</a>{data.fromApi ? ` and API-Football (${data.fromApi} recent matches)` : ''}.</div>
	</div>
</section>
