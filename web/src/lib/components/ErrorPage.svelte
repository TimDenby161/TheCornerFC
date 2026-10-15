<script lang="ts">
	import { page } from '$app/state';

	// What a visitor sees when a page can't be shown: plain words, never the fault itself (that is
	// logged by hooks.server.ts and hooks.client.ts), and a way on. No back button: the browser has one.
	const missing = $derived(page.status === 404);
	const again = $derived(page.url.pathname + page.url.search);
</script>

<svelte:head><title>{missing ? 'Page not found' : 'Something went wrong'} · The Corner FC</title></svelte:head>

<div class="empty-state not-found error-page" role="status">
	{#if missing}
		<h2>Page not found</h2>
		<p>There's no page at this address. The link may be old, or mistyped.</p>
		<p class="error-links"><a class="mt-btn" href="/">Home</a> <a class="mt-btn" href="/clubs">Clubs</a></p>
	{:else}
		<h2>Something went wrong</h2>
		<p>This page couldn't be shown just now. The problem is on our side, and it's usually over in a moment.</p>
		<p class="error-links"><a class="mt-btn" href={again} data-sveltekit-reload>Try again</a> <a class="mt-btn" href="/">Home</a></p>
	{/if}
</div>
