<script lang="ts">
	import { handlesRange, rangeLabel, rangeText, type RangeKey } from '#lib/playerFilters.ts';

	// A two-handled slider over a list of stops. A handle at either end leaves that end open. The
	// handles and the words beside the name move straight away; `pick` is told the range once the
	// handle has settled (null: both ends open).
	let { kind, name, stops, a: fromA, b: fromB, pick, ids }:
		{ kind: RangeKey; name: string; stops: number[]; a: number; b: number; pick: (range: string | null) => void; ids?: [string, string] } = $props();

	// where the address puts the handles (so the server draws them there), then wherever they are
	// dragged; when the address changes, they follow it
	// svelte-ignore state_referenced_locally
	let a = $state(fromA), b = $state(fromB);
	$effect(() => { a = fromA; b = fromB; });
	const n = $derived(stops.length - 1);
	const at = (i: number) => Math.round((i / (n || 1)) * 100);

	let settle: ReturnType<typeof setTimeout> | undefined;
	function moved(end: 0 | 1, e: Event, done: boolean) {
		const v = Number((e.currentTarget as HTMLInputElement).value);
		// handles can't cross
		if (end === 0) a = Math.min(v, b); else b = Math.max(v, a);
		(e.currentTarget as HTMLInputElement).value = String(end === 0 ? a : b);
		clearTimeout(settle);
		const tell = () => pick(rangeText(handlesRange(stops, a, b)));
		if (done) tell(); else settle = setTimeout(tell, 250);
	}
</script>

<div class="age-head"><span>{name}</span><span class="rng-val">{rangeLabel(kind, stops, a, b)}</span></div>
<div class="age-slider">
	<div class="age-track"><div class="age-fill sx-{at(a)} sr-{100 - at(b)}"></div></div>
	<input type="range" min="0" max={n} step="1" value={a} id={ids?.[0]} aria-label="{name}: from" oninput={(e) => moved(0, e, false)} onchange={(e) => moved(0, e, true)} />
	<input type="range" min="0" max={n} step="1" value={b} id={ids?.[1]} aria-label="{name}: to" oninput={(e) => moved(1, e, false)} onchange={(e) => moved(1, e, true)} />
</div>
