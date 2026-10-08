<script lang="ts">
	import RankChart from '#lib/components/RankChart.svelte';
	import { rankTier } from '#lib/club.ts';

	let { data } = $props();
	type SpellView = (typeof data.now)[number];
</script>

<svelte:head>
	<title>{data.name} career · The Corner FC</title>
	<meta name="description" content="{data.name} season by season: his rank, clubs, minutes, goals and assists, and the positions he played." />
</svelte:head>

{#snippet spellList(list: SpellView[])}
	{#each list as x, i (i)}
		<div class="spell"><a class="team-link" href="/club/{x.team}">{x.name}</a>
			<span class="dim"> · club {x.clubRank ?? '–'} · {x.minutes ? `${x.minutes.toLocaleString('en-GB')}′` : 'no minutes here'}{x.minutes ? ` · ${x.goals} G, ${x.assists} A` : ''}</span></div>
	{/each}
{/snippet}

{#if data.points.length}
	<div class="chart-card"><div class="chart-head"><span class="chart-title">Season ranks</span></div>
		<RankChart points={data.points} name={data.name} /></div>
{/if}
<div class="club-section" class:u-mt0={!data.points.length}><div class="modal-section">Season by season</div>
	{#if data.rows.length}
		<table class="season-table"><thead><tr><th>Season</th><th>Clubs · club Elo · minutes · goals, assists</th><th class="num">Rank</th></tr></thead>
			<tbody>
				{#each data.rows as r (r.y)}
					<tr><td class="num u-left">{r.label}<div class="dim">{r.age != null ? `age ${r.age}` : ''}</div></td>
						<td>{#if r.spells.length}{@render spellList(r.spells)}{:else}<span class="dim">{r.est ? 'Estimated from his other seasons and age' : ''}</span>{/if}
							{#if r.shares.length || r.ratedAs}<div class="pos-shares">{#each r.shares as s (s.label)}<span class="pos-share" class:sub={s.other}>{s.label} {s.pct}%</span>{/each}{#if r.ratedAs}<span class="rated-as">rated as {r.ratedAs}</span>{/if}</div>{/if}</td>
						<td class="num">{#if r.est}<span class="est"><span class="rel-chip rel-{rankTier(r.rank)}">{Math.round(r.rank)}</span></span>{:else}<span class="rel-chip rel-{rankTier(r.rank)}">{Math.round(r.rank)}</span>{/if}</td></tr>
				{/each}
			</tbody></table>
		<div class="page-note">A season's rank starts from his clubs' level (LT ALGO over his matches) and his stats against players in his position, then follows the typical age curve for his position from a level of his own: a season only moves off that curve as far as its minutes justify. Outlined ranks are estimated.</div>
	{:else}
		<div class="pl-callout">His season ranks are for subscribers.</div>
	{/if}
</div>
{#if data.now.length}
	<div class="club-section"><div class="modal-section">His current rank is built on · last 20 appearances</div><div class="season-now">{@render spellList(data.now)}</div></div>
{/if}
