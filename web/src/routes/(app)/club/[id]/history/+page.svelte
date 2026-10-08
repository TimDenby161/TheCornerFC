<script lang="ts">
	import { pct } from '#lib/club.ts';

	let { data } = $props();
	const move = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;
</script>

<svelte:head>
	<title>{data.name} history · The Corner FC</title>
	<meta name="description" content="{data.name} season by season since 2020: league, record, goals and strength rating at the end of each season." />
</svelte:head>

{#if !data.seasons.length}
	<div class="empty-state">No match history for this club yet.</div>
{:else}
	<div class="chart-card"><div class="chart-head"><span class="chart-title">Elo at the end of each season</span></div>
		<div class="season-bars">
			{#each data.seasons.slice().reverse() as s (s.y)}
				<div class="season-bar" title="{s.label}: {s.end.toFixed(1)}"><span class="sb-val">{Math.round(s.end)}</span>
					<div class="sb-fill sh-{pct(s.bar)}"></div><span class="sb-label">{s.label}</span></div>
			{/each}
		</div></div>
	<div class="club-section"><div class="modal-section">Season by season</div>
		<table class="season-table"><thead><tr><th>Season</th><th>League · record · goals</th><th class="num">Elo</th><th class="num">Change</th></tr></thead>
			<tbody>
				{#each data.seasons as s, i (s.y)}
					<tr>
						<td class="num u-left">{s.label}{#if i === 0}<div class="dim">so far</div>{/if}</td>
						<td>{#if s.leagueName}{s.leagueName}{:else}<span class="dim">Cups only</span>{/if}
							<div class="dim">{s.played} played · {s.w}W {s.d}D {s.l}L · {s.gf}–{s.ga}</div></td>
						<td class="num">{Math.round(s.end)}<div class="dim">high {Math.round(s.peak)}</div></td>
						<td class="num">{#if s.start != null}{@const v = s.end - s.start}<span class={v > 0 ? 'form-up' : v < 0 ? 'form-down' : ''}>{move(v)}</span>{/if}</td>
					</tr>
				{/each}
			</tbody></table>
		<div class="page-note">Elo: the club's Elo rating after its last match of the season; change: over the season. All competitions.</div></div>
{/if}
