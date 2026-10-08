<script lang="ts">
	// (this site's own copy: it names the host and the cookies of this app, where the old site's
	// page, docs/privacy.html, names its own)
	import raw from '../../../text/privacy.html?raw';
	import { textPage } from '#lib/textPage.ts';

	const page = textPage(raw);
</script>

<svelte:head><title>{page.title}</title><meta name="description" content={page.description} /></svelte:head>

<!-- eslint-disable-next-line svelte/no-at-html-tags -- the site's own file, read at build time -->
{@html page.html}
