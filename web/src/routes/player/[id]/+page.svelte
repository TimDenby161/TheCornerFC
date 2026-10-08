<script lang="ts">
	import Crest from '#lib/components/Crest.svelte';
	import LocalTime from '#lib/components/LocalTime.svelte';
	import { rankTier } from '#lib/club.ts';

	let { data } = $props();
	const now = $derived(data.now);
</script>

<svelte:head>
	<title>{data.name} · The Corner FC</title>
	<meta name="description" content="{data.name}{data.team ? ` (${data.team.name})` : ''}: Ability rank, this season's minutes, goals and assists, recent appearances and positions." />
</svelte:head>

{#if data.next}
	{@const n = data.next}
	<div class="next-card">
		<div class="next-top"><span class="next-label">{n.live ? 'Live now' : 'Next match'}</span>
			<span><LocalTime iso={n.kickoff} show="day" /> · <LocalTime iso={n.kickoff} show="time" /></span></div>
		<div class="next-opp"><Crest id={n.opp} name={n.oppName} href="/club/{n.opp}" />
			<span class="next-opp-name">{n.home ? 'v' : '@'} <a class="team-link" href="/club/{n.opp}">{n.oppName}</a></span></div>
		<div class="next-meta"><span>{n.comp}</span>{#if n.win != null}<span>{n.win}% win</span>{/if}{#if n.proj}<span>projected {n.proj}</span>{/if}</div>
		{#if n.status}<div class="next-status {n.status.cls}">{n.status.text}</div>{/if}
	</div>
{/if}

{#if data.chips.length}
	<div class="club-section pos-section">
		<div class="pos-row">
			{#each data.chips as c (c.group)}
				<div class="pos-chip rel-{rankTier(c.rank)}" class:main={c.main} title="{c.name}: rank {c.rank.toFixed(1)} · {c.pct ? `${c.pct}% of his starting minutes` : 'no starts here'}">
					<span class="pos-chip-pos">{c.group}</span><span class="pos-chip-rank">{Math.round(c.rank)}</span>
					<span class="pos-chip-pct">{c.pct ? `${c.pct}%` : '–'}</span></div>
			{/each}
		</div>
	</div>
{/if}

<div class="club-section pl-block">
	<div class="modal-section">Current Season · {data.seasonName}</div>
	{#if now?.minutes}
		<div class="team-stats compact">
			<div class="team-stat"><div class="team-stat-label">Minutes</div><div class="team-stat-value">{now.minutes.toLocaleString('en-GB')}</div>{#if now.apps != null}<div class="team-stat-sub">{now.apps} apps{now.starts != null ? ` · ${now.starts} started` : ''}</div>{/if}</div>
			{#if !data.keeper}
				<div class="team-stat"><div class="team-stat-label">Goals</div><div class="team-stat-value">{now.goals ?? '–'}</div></div>
				<div class="team-stat"><div class="team-stat-label">Assists</div><div class="team-stat-value">{now.assists ?? '–'}</div></div>
			{/if}
		</div>
		{#if now.minutes < 900}<div class="page-note">Only {now.minutes.toLocaleString('en-GB')} minutes so far: this season moves his Ability only a little until he plays more.</div>{/if}
	{:else}
		<div class="pl-callout">No league minutes in {data.seasonName} yet{data.listed ? ` · listed ${data.listed}` : ''}.
			{#if data.rank != null}His Ability of {data.rank} comes from earlier seasons and his age curve, not from current form.{/if}</div>
	{/if}
</div>
