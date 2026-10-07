<script lang="ts">
	import { OLD_SITE } from '#lib/menu.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>{data.name} predicted XI · The Corner FC</title>
	<meta name="description" content="The line-up the model expects {data.name} to start in their next match." />
</svelte:head>

{#if data.paywall}
	<div class="empty-state">Predicted line-ups are for subscribers.</div>
{:else}
	<div class="empty-state">The predicted XI is on <a href="{OLD_SITE}#/club/{data.id}/xi">this club's page on the current site</a> until it is rebuilt here.</div>
{/if}
