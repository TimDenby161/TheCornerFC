<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import SubscriberLink from '#lib/components/SubscriberLink.svelte';
	import { chanceText, projectable, projectGroup, SIMS, type Projected } from '#lib/league.ts';

	let { data } = $props();
	// The rest of the season is played out in the browser once the page is showing (it takes a
	// moment), group by group; until then the page says so.
	let played = $state<Projected[][] | null>(null);
	$effect(() => {
		if (data.mode !== 'full' || !data.left) return;
		played = null;
		const groups = data.groups, fixtures = projectable(data.fixtures);
		const t = setTimeout(() => { played = groups.map((g) => projectGroup(g.rows, fixtures)); }, 30);
		return () => clearTimeout(t);
	});
</script>

<svelte:head>
	<title>{data.label} projected table · The Corner FC</title>
	<meta name="description" content="Where the model expects each {data.label} club to finish, and on how many points." />
</svelte:head>

{#snippet legend()}{#if data.legend.length}<div class="lt-legend">{#each data.legend as z (z.text)}<span><i class={z.cls}></i>{z.text}</span>{/each}</div>{/if}{/snippet}

{#if data.mode === 'headline'}
	{#if !data.groups.length}
		<div class="empty-state">The projected table and each club's finishing chances are for subscribers. <SubscriberLink /></div>
	{:else}
		{#each data.groups as g (g.name)}
			{#if data.several}<div class="modal-section">{g.name}</div>{/if}
			<div class="table-scroll"><table class="league-table">
				<thead><tr><th class="lt-pos">#</th><th></th><th class="lt-club">Club</th>
					<th class="lt-wide" title="Matches left to play">Left</th><th title="Projected points: points so far plus the points the model expects from the matches left">Pts</th></tr></thead>
				<tbody>
					{#each g.rows as x (x.team)}
						<tr><td class="lt-pos {x.zone}">{x.place}</td>
							<td class="lt-badge"><Crest id={x.team} name={x.name} href="/club/{x.team}" /></td>
							<td class="lt-club"><a class="team-link" href="/club/{x.team}">{x.name}</a></td>
							<td class="lt-wide">{x.left}</td><td><b>{x.points}</b></td></tr>
					{/each}
				</tbody>
			</table></div>
		{/each}
		{@render legend()}
		<div class="page-note">Projected places and points. Projected wins, draws, losses and goal difference, and each club's chance of finishing in every place, are for subscribers. <SubscriberLink /></div>
	{/if}
{:else if !data.left}
	<div class="empty-state">No upcoming matches to project.</div>
{:else if !played}
	<div class="empty-state">Playing out the rest of the season…</div>
{:else}
	{#each data.groups as g, k (g.name)}
		{#if data.several}<div class="modal-section">{g.name}</div>{/if}
		<div class="table-scroll"><table class="league-table">
			<thead><tr><th class="lt-pos">#</th><th></th><th class="lt-club">Club</th>
				<th class="lt-wide" title="Matches left to play">Left</th><th class="lt-wdl" title="Projected wins">W</th><th class="lt-wdl" title="Projected draws">D</th><th class="lt-wdl" title="Projected losses">L</th>
				<th class="lt-gd" title="Projected goal difference">GD</th><th title="Projected points: points so far plus the average over the simulated seasons">Pts</th>
				<th class="lt-chance" title="Chance of finishing top">1st</th>{#each g.cols as c (c.text)}<th title={c.text}><i class="lt-zone {c.cls}"></i></th>{/each}</tr></thead>
			<tbody>
				{#each played[k] as x, i (x.team)}
					<tr><td class="lt-pos {g.zones[i] ?? ''}">{i + 1}</td>
						<td class="lt-badge"><Crest id={x.team} name={data.names[x.team]} href="/club/{x.team}" /></td>
						<td class="lt-club"><a class="team-link" href="/club/{x.team}">{data.names[x.team]}</a></td>
						<td class="lt-wide">{x.left}</td><td class="lt-wdl">{Math.round(x.w)}</td><td class="lt-wdl">{Math.round(x.d)}</td><td class="lt-wdl">{Math.round(x.l)}</td>
						<td class="lt-gd">{x.gd >= 0.5 ? '+' : ''}{Math.round(x.gd)}</td><td><b>{Math.round(x.pts)}</b></td>
						<td class="lt-chance" class:dim={x.pos[0] <= 0}>{chanceText(x.pos[0])}</td>
						{#each g.cols as c (c.text)}{@const p = c.places.reduce((a, place) => a + (x.pos[place] || 0), 0)}<td class:dim={p <= 0}>{chanceText(p)}</td>{/each}</tr>
				{/each}
			</tbody>
		</table></div>
	{/each}
	{@render legend()}
	<div class="page-note">The {data.left.toLocaleString('en-GB')} scheduled matches left, played out {SIMS.toLocaleString('en-GB')} times from the model's predicted scores and home · draw · away chances, on top of the current table. Each simulated season also varies every club's true strength a little, since ratings are estimates and a club that is better or worse than rated is so all season. The figures are chances, not a forecast of one outcome. Level clubs are split by goal difference, then goals scored. Matches not yet scheduled (play-offs, split rounds) aren't included.</div>
{/if}
