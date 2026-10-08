<script lang="ts">
	import { page } from '$app/state';
	import type { Snippet } from 'svelte';
	import type { Sort } from '#lib/league.ts';

	// A column heading that sorts its table: the first press sorts the column best first, a second
	// reverses it. The choice is in the address (?sort=points, &rev=1 reversed); `def` is the
	// table's own order, which is left out.
	let { key, sort, def, title, cls = '', children }: { key: string; sort: Sort; def: string; title: string; cls?: string; children: Snippet } = $props();
	const on = $derived(sort.key === key);
	const href = $derived.by(() => {
		const q = new URLSearchParams(page.url.search);
		q.delete('sort'); q.delete('rev');
		if (on) { if (key !== def) q.set('sort', key); if (!page.url.searchParams.has('rev')) q.set('rev', '1'); }
		else if (key !== def) q.set('sort', key);
		const s = q.toString();
		return s ? `?${s}` : page.url.pathname;
	});
</script>

<th class="{cls} sortable" class:active={on} title="{title}. Click to sort." aria-sort={on ? (sort.dir > 0 ? 'ascending' : 'descending') : undefined}>
	<a {href} data-sveltekit-reset="false">{@render children()}{#if on}<span class="sort-dir">{sort.dir > 0 ? '▲' : '▼'}</span>{/if}</a>
</th>
