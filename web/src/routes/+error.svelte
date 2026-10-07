<script lang="ts">
	import { page } from '$app/state';
</script>

<svelte:head><title>{page.status === 404 ? 'Page not found' : 'Something went wrong'} · The Corner FC</title></svelte:head>

<section class="panel" data-tab="club" data-active="true">
	<div class="empty-state not-found" role="status">
		{#if page.status === 404}
			<h2>Page not found</h2><p>There's no page at this address.</p>
		{:else}
			<h2>Couldn't load this page</h2><p>The data didn't arrive. Try again in a moment.</p>
		{/if}
		<a class="mt-btn" href="/clubs">Go to Clubs</a>
	</div>
</section>
