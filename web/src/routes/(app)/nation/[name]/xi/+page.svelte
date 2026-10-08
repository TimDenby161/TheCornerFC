<script lang="ts">
	import PersonChip from '#lib/components/PersonChip.svelte';
	import XiPitch from '#lib/components/XiPitch.svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.name} predicted XI · The Corner FC</title>
	<meta name="description" content="The eleven {data.name}'s coach is most likely to start, read off his recent team sheets." />
</svelte:head>

{#if data.state === 'none'}
	<div class="empty-state">No line-ups for {data.name} yet (they come from API-Football's international matches).</div>
{:else if data.state === 'few'}
	<div class="empty-state">Not enough line-ups to predict {data.name}'s XI yet.</div>
{:else}
	{#snippet pitch()}<div class="club-section pp-section"><XiPitch spots={data.state === 'xi' ? data.spots : []} /></div>{/snippet}
	{#if data.out.length}
		<div class="ov-top"><div class="ov-side">
			<div class="next-card"><div class="next-top"><span class="next-label">Out injured</span></div>
				{#each data.out as o (o.id)}
					<div class="nat-xi-row"><span class="nat-xi-who"><PersonChip name={o.name} />{#if o.link}<a class="player-link" href="/player/{o.id}">{o.short}</a>{:else}<span title={o.name}>{o.short}</span>{/if}</span></div>
				{/each}
			</div>
		</div>{@render pitch()}</div>
	{:else}
		{@render pitch()}
	{/if}
{/if}
