<script lang="ts">
	import { page } from '$app/state';
	import Crest from '#lib/components/Crest.svelte';
	import PersonChip from '#lib/components/PersonChip.svelte';

	let { data } = $props();
	const COLS = [
		['apps', 'Apps', 'Matches played, starting or from the bench.'], ['minutes', 'Mins', "Minutes played (where API-Football has the player's stat line)."],
		['goals', 'G', 'Goals.'], ['assists', 'A', 'Assists.'], ['cards', 'Cards', 'Yellow and red cards.'], ['last', 'Last', 'Date of his latest appearance.']
	];
</script>

<svelte:head>
	<title>{data.name} players · The Corner FC</title>
	<meta name="description" content="Everyone who has played for {data.name} under the current head coach: appearances, minutes, goals, assists and cards." />
</svelte:head>

{#if !data.any}
	<div class="empty-state">No line-ups for {data.name} yet (they come from API-Football's international matches).</div>
{:else}
	<div class="modal-section nat-spell">{data.heading}</div>
	<div class="table-scroll"><table class="leaderboard nat-players">
		<thead><tr><th>#</th><th>Player</th><th title="His most common starting role in these matches (else his club position).">Pos</th>
			{#each COLS as [key, label, tip] (key)}
				<th class="num sortable" class:active={data.sort === key} aria-sort={data.sort === key ? 'descending' : undefined} title="{tip} Click to sort."><a href={key === 'minutes' ? page.url.pathname : `?sort=${key}`} data-sveltekit-reset="false">{label}</a></th>
			{/each}
		</tr></thead>
		<tbody>
			{#each data.players as p, i (p.id)}
				<tr>
					<td>{i + 1}</td>
					<td><div class="club-cell"><PersonChip name={p.name} />{#if p.link}<a class="player-link" href="/player/{p.id}">{p.short}</a>{:else}<span title={p.name}>{p.short}</span>{/if}
						{#if p.team && p.teamName}<a class="pl-badge-link nat-badge" href="/club/{p.team}" title={p.teamName} aria-label={p.teamName}><Crest id={p.team} name={p.teamName} /></a>{/if}</div></td>
					<td>{p.role}</td>
					<td class="num">{p.apps}</td>
					<td class="num" title={p.noMins ? `Minutes not known for ${p.noMins} of his matches` : undefined}>{p.noMins === p.apps ? '–' : `${p.minutes}${p.noMins ? '*' : ''}`}</td>
					<td class="num">{p.goals || ''}</td><td class="num">{p.assists || ''}</td>
					<td class="num">{#if p.y}<span class="card-y" title="Yellow cards">{p.y}</span>{/if}{#if p.r}<span class="card-r" title="Red cards">{p.r}</span>{/if}</td>
					<td class="num">{p.lastText}</td>
				</tr>
			{/each}
		</tbody>
	</table></div>
	<div class="page-note">{data.players.length} players in {data.matches} matches, from API-Football's line-ups and player stats. Click a heading to sort.{data.anyNoMins ? " * Includes starts with no stat line, whose minutes aren't known." : ''}</div>
{/if}
