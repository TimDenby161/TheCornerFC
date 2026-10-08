<script lang="ts">
	import ClubRatingTable from '#lib/components/ClubRatingTable.svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.label} strength ranking · The Corner FC</title>
	<meta name="description" content="The {data.label}'s clubs ranked by strength rating, beside where each sits in the table." />
</svelte:head>

{#if data.rows.length}
	<ClubRatingTable rows={data.rows} sort={data.sort} def="lt" table={data.hasTable} />
	<div class="page-note">Baseline: Baseline Strength, the long-term Elo rating. Current: Current Strength, the Elo rating now. Gap: Current minus Baseline. Last 6: the change in Elo over the club's last 6 matches.</div>
{:else}
	<div class="empty-state">No ranked clubs.</div>
{/if}
