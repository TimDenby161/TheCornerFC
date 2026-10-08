<script lang="ts">
	import raw from '../../../../../docs/privacy.html?raw';
	import { textPage } from '#lib/textPage.ts';

	const page = textPage(raw);
</script>

<svelte:head><title>{page.title}</title><meta name="description" content={page.description} /></svelte:head>

<!-- eslint-disable-next-line svelte/no-at-html-tags -- the site's own file, read at build time -->
{@html page.html}
