<script lang="ts">
	import { COUNTRY_FIRST, CONTINENTS, regionLabel } from '#lib/names.ts';

	// Exclude: the big five countries and the continents, hidden from a list on top of its menu.
	// Each chip's button carries the list as it would be after the press ("ex" in the address);
	// `keep` is the page's other choices. `what`: "clubs" or "players", for the hover text.
	let { excluded, action, keep = {}, what = 'club' }: { excluded: string[]; action: string; keep?: Record<string, string>; what?: string } = $props();
	const ex = $derived(new Set(excluded));
	const toggled = (...keys: string[]) => {
		const next = new Set(ex);
		const all = keys.every((k) => next.has(k));
		for (const k of keys) if (all) next.delete(k); else next.add(k);
		return [...next].join('|');
	};
</script>

<div id="exclude-filter">
	<form class="contents" method="get" {action} data-sveltekit-reset="false">
		{#each Object.entries(keep) as [k, v] (k)}<input type="hidden" name={k} value={v} />{/each}
		<div class="pos-head"><span>Exclude</span>
			<button type="submit" class="pos-clear" hidden={!ex.size}>Clear</button></div>
		<div class="ex-chips">
			<button type="submit" name="ex" value={toggled(...COUNTRY_FIRST)} class="filter-chip ex-chip" aria-pressed={COUNTRY_FIRST.every((c) => ex.has(c))} title="Exclude {COUNTRY_FIRST.join(', ')}">Big 5</button>
			{#each COUNTRY_FIRST as c (c)}
				<button type="submit" name="ex" value={toggled(c)} class="filter-chip ex-chip" aria-pressed={ex.has(c)} title="Exclude {c}'s {what}s">{c}</button>
			{/each}
			<span class="ex-break"></span>
			{#each CONTINENTS as r (r)}
				<button type="submit" name="ex" value={toggled(`r:${r}`)} class="filter-chip ex-chip" aria-pressed={ex.has(`r:${r}`)} title="Exclude every {what} in {r}{r === 'Europe' ? ' (the big five included)' : ''}">{regionLabel(r)}</button>
			{/each}
		</div>
	</form>
</div>
