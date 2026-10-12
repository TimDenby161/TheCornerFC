<script lang="ts">
	import { scale, ticks } from '#lib/changes.ts';

	// One or more lines over the same run of labels (months, or changes in the order they went
	// live). Drawn 640 wide and scaled to its box; every position is an SVG attribute.
	type Series = { name: string; cls: string; points: { x: string; value: number; note?: string }[] };
	let { series, label, places = 3, zero = false }: { series: Series[]; label: string; places?: number; zero?: boolean } = $props();
	const W = 640, H = 240, L = 58, R = 14, T = 12, B = 30;
	const xs = $derived([...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort());
	const values = $derived(series.flatMap((s) => s.points.map((p) => p.value)));
	const lo = $derived(Math.min(...values, ...(zero ? [0] : []))), hi = $derived(Math.max(...values, ...(zero ? [0] : [])));
	const pad = $derived((hi - lo || Math.abs(hi) || 1) * 0.08);
	const y = $derived(scale([lo - pad, hi + pad], [H - B, T]));
	const x = $derived((label: string) => (xs.length < 2 ? (L + W - R) / 2 : scale([0, xs.length - 1], [L, W - R])(xs.indexOf(label))));
	const marks = $derived(ticks(lo - pad, hi + pad));
	// about six labels along the foot, however many points there are
	const every = $derived(Math.max(1, Math.ceil(xs.length / 6)));
	const path = (s: Series) => s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
</script>

<figure class="mc-chart">
	<svg viewBox="0 0 {W} {H}" role="img" aria-label={label}>
		<g class="chart-grid">{#each marks as v (v)}<line x1={L} x2={W - R} y1={y(v).toFixed(1)} y2={y(v).toFixed(1)} />{/each}</g>
		<g class="chart-axis">
			{#each marks as v (v)}<text x={L - 6} y={(y(v) + 3).toFixed(1)} text-anchor="end">{v.toFixed(places)}</text>{/each}
			{#each xs as tick, i (tick)}{#if i % every === 0}<text x={x(tick).toFixed(1)} y={H - 8} text-anchor="middle">{tick}</text>{/if}{/each}
		</g>
		{#if zero}<line class="mc-zero" x1={L} x2={W - R} y1={y(0).toFixed(1)} y2={y(0).toFixed(1)} />{/if}
		{#each series as s (s.name)}
			<path class="mc-line {s.cls}" d={path(s)} />
			{#if s.points.length <= 24}{#each s.points as p (p.x)}<circle class="mc-dot {s.cls}" cx={x(p.x).toFixed(1)} cy={y(p.value).toFixed(1)} r="3.5"><title>{p.x}: {p.value.toFixed(places + 1)}{p.note ? ` · ${p.note}` : ''}</title></circle>{/each}{/if}
		{/each}
	</svg>
	<figcaption class="mc-legend">{#each series as s (s.name)}<span><i class="mc-key {s.cls}" aria-hidden="true"></i>{s.name}</span>{/each}</figcaption>
</figure>
