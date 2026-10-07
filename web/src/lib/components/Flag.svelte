<script lang="ts">
	import { FLAG_CODES } from '#lib/names.ts';
	import { pageHref } from '#lib/menu.ts';

	// A country's flag, linking to its page (its name where there is no flag). `key` is the
	// country as the data names it ("Saudi-Arabia"), `name` as it is shown.
	let { key, name }: { key: string; name: string } = $props();
	const code = $derived(FLAG_CODES[name]);
</script>

{#if code}<a class="flag-link" href={pageHref('country', key)} title={name} aria-label={name}><img class="flag" src="https://flagcdn.com/w40/{code}.png" alt="" loading="lazy" /></a>{:else}<a class="nat-link" href={pageHref('country', key)}>{name}</a> ·{/if}
