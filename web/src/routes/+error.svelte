<script lang="ts">
	// A failed page outside the site's own (an address with no page, the plain text pages): the
	// same words. Its look is its own and scoped here: this component is loaded with every page,
	// so a stylesheet imported here would reach the whole site.
	import ErrorPage from '#lib/components/ErrorPage.svelte';
</script>

<main class="root-error"><ErrorPage /></main>

<style>
	.root-error {
		--ink: #0d1410;
		--soft: #414b45;
		min-height: 100vh;
		box-sizing: border-box;
		background: #f4f5ef;
		color: var(--ink);
		font-family: Archivo, system-ui, sans-serif;
		padding: 0 16px;
	}
	@media (prefers-color-scheme: dark) {
		.root-error { --ink: #eef1e8; --soft: #b8c1b7; background: #0b110e; }
	}
	.root-error :global(.error-page) { text-align: center; padding: clamp(40px, 12vh, 120px) 0; }
	.root-error :global(h2) { margin: 0 0 8px; font-size: clamp(28px, 4vw, 44px); line-height: 1; font-weight: 900; text-transform: uppercase; }
	.root-error :global(p) { margin: 0 0 20px; font-size: 15px; color: var(--soft); }
	.root-error :global(.error-links) { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }
	.root-error :global(.mt-btn) { display: inline-block; padding: 8px 14px; border: 2px solid var(--ink); color: var(--ink); text-decoration: none; font-weight: 700; }
</style>
