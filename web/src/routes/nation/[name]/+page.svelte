<script lang="ts">
	import { page } from '$app/state';
	import Pitch from '#lib/components/Pitch.svelte';
	import SubscriberLink from '#lib/components/SubscriberLink.svelte';
	import { rankTier } from '#lib/club.ts';

	let { data } = $props();
	const allHref = $derived.by(() => { const q = new URLSearchParams(page.url.search); q.set('all', '1'); return `?${q}`; });
</script>

<svelte:head>
	<title>{data.name} · The Corner FC</title>
	<meta name="description" content="{data.name}: the national team's rating, its best players by position and every ranked {data.name} player." />
</svelte:head>

{#if !data.total}
	<div class="empty-state">No ranked players from {data.name}.</div>
{:else}
	{#if data.pitch}
		<div class="club-section"><div class="modal-section">{data.pitch.hasShape ? `Best by current rank in their usual ${data.pitch.formation}` : 'Top 3 in each position by current rank'}</div>
			<div class="pp-section">
				<Pitch kind="dp-pitch">
					{#each data.pitch.boxes as b (b.label)}
						{#if b.players.length}
							<div class="dp-spot gr-{b.row} gc-{b.col}"><span class="dp-pos">{b.label}</span>
								{#each b.players as p (p.id)}
									{#if p.link}
										<a class="dp-row nat-row" class:nat-unpicked={p.unpicked} href="/player/{p.id}" title={p.tip}><span class="dp-name">{p.name}</span><span class="dp-rank {p.rank == null ? '' : `t${rankTier(p.rank)}`}">{p.rank ?? '–'}</span></a>
									{:else}
										<span class="dp-row nat-row" class:nat-unpicked={p.unpicked} title={p.tip}><span class="dp-name">{p.name}</span><span class="dp-rank">–</span></span>
									{/if}
								{/each}
							</div>
						{:else}
							<div class="dp-spot empty gr-{b.row} gc-{b.col}"><span class="dp-pos">{b.label}</span></div>
						{/if}
					{/each}
				</Pitch>
				{#if data.pitch.hasShape}<div class="page-note u-center">Plus everyone {data.pitch.coach || 'the current coach'} has picked. <span class="nat-unpicked-key">Red</span>: not picked by him.</div>{/if}
			</div>
		</div>
	{/if}
	{#if data.paywall}<div class="pl-callout">Player ranks outside the top 50 overall, the top 10 in each league and the top 10 in each position are for subscribers: his rank, season by season, in each position and projected. <SubscriberLink /></div>{/if}
	<div class="club-section"><div class="modal-section">All players</div>
		<div>
			{#each data.players as p, i (p.id)}
				<div class="team-row"><span class="team-row-date">{i + 1}. {p.position}</span>
					<span class="team-row-opp"><a class="player-link" href="/player/{p.id}">{p.name}</a>{' '}<span class="club-sub u-inline">{#if p.team}<a class="team-link" href="/club/{p.team}">{p.teamName}</a>{:else}<span class="dim-text">club not known</span>{/if}{p.age != null ? ` · ${p.age}` : ''}</span></span>
					<span class="team-row-res">{#if p.rank == null}–{:else}<span class="rel-chip rel-{rankTier(p.rank)}">{Math.round(p.rank)}</span>{/if}</span></div>
			{/each}
		</div>
		{#if !data.showAll && data.total > data.players.length}<a class="show-all" href={allHref} data-sveltekit-reset="false">Show all {data.total.toLocaleString('en-GB')}</a>{/if}
	</div>
{/if}
