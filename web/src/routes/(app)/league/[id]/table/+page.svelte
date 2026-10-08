<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import SortTh from '#lib/components/SortTh.svelte';

	let { data } = $props();
	const s = $derived(data.sort);
</script>

<svelte:head>
	<title>{data.label} table · The Corner FC</title>
	<meta name="description" content="The {data.label} table this season, with each club's form and current strength rating." />
</svelte:head>

{#each data.groups as g (g.name)}
	{#if data.several}<div class="modal-section">{g.name}</div>{/if}
	<div class="table-scroll"><table class="league-table">
		<thead><tr>
			<SortTh key="rank" sort={s} def="rank" title="Position" cls="lt-pos">#</SortTh><th></th>
			<SortTh key="club" sort={s} def="rank" title="Club name" cls="lt-club">Club</SortTh>
			<SortTh key="played" sort={s} def="rank" title="Played">P</SortTh>
			<SortTh key="win" sort={s} def="rank" title="Won" cls="lt-wdl">W</SortTh><SortTh key="draw" sort={s} def="rank" title="Drawn" cls="lt-wdl">D</SortTh><SortTh key="lose" sort={s} def="rank" title="Lost" cls="lt-wdl">L</SortTh>
			<SortTh key="gf" sort={s} def="rank" title="Goals for" cls="lt-wide">GF</SortTh><SortTh key="ga" sort={s} def="rank" title="Goals against" cls="lt-wide">GA</SortTh>
			<SortTh key="gd" sort={s} def="rank" title="Goal difference" cls="lt-gd">GD</SortTh><SortTh key="points" sort={s} def="rank" title="Points">Pts</SortTh>
			{#if data.hasXg}
				<SortTh key="xg90" sort={s} def="rank" title="Expected goals per 90 minutes over the club's last five league games, estimated from its shots">xG/90</SortTh>
				<SortTh key="xga90" sort={s} def="rank" title="Expected goals conceded per 90 minutes over the club's last five league games, estimated from the shots it faced">xGC/90</SortTh>
			{/if}
			<SortTh key="form" sort={s} def="rank" title="Last five league games, newest first: green won, grey drawn, red lost. Sorts by points from them" cls="lt-formcol">Form</SortTh>
			<SortTh key="current" sort={s} def="rank" title="Current Strength: the club's current Elo rating">Current</SortTh>
		</tr></thead>
		<tbody>
			{#each g.rows as r (r.team)}
				{@const xgTip = r.xg_games ? `Over the last ${r.xg_games} league game${r.xg_games === 1 ? '' : 's'} with shot counts` : undefined}
				<tr><td class="lt-pos {r.zone}">{r.rank}</td>
					<td class="lt-badge"><Crest id={r.team} name={r.name} href="/club/{r.team}" /></td>
					<td class="lt-club"><a class="team-link" href="/club/{r.team}">{r.name}</a></td>
					<td>{r.played ?? ''}</td><td class="lt-wdl">{r.win ?? ''}</td><td class="lt-wdl">{r.draw ?? ''}</td><td class="lt-wdl">{r.lose ?? ''}</td>
					<td class="lt-wide">{r.gf ?? ''}</td><td class="lt-wide">{r.ga ?? ''}</td><td class="lt-gd">{r.gd != null && r.gd > 0 ? '+' : ''}{r.gd ?? ''}</td><td><b>{r.points ?? ''}</b></td>
					{#if data.hasXg}<td title={xgTip}>{r.xg90 != null ? r.xg90.toFixed(2) : ''}</td><td title={xgTip}>{r.xga90 != null ? r.xga90.toFixed(2) : ''}</td>{/if}
					<td class="lt-formcol">{#if r.form}<span class="lt-form">{#each [...r.form] as c, i (i)}<i class={c === 'W' ? 'res-w' : c === 'D' ? 'res-d' : 'res-l'}>{c}</i>{/each}</span>{/if}</td>
					<td class="lt-elo">{r.current != null ? Math.round(r.current) : ''}</td></tr>
			{/each}
		</tbody>
	</table></div>
{/each}
{#if data.legend.length}<div class="lt-legend">{#each data.legend as z (z.text)}<span><i class={z.cls}></i>{z.text}</span>{/each}</div>{/if}
