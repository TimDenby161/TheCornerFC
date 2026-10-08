<script lang="ts">
	import { chartLayout, type ChartPoint } from '#lib/player.ts';

	// Season ranks as a line, drawn to the width of its box so the text stays readable on phones
	// (the server draws it 640 wide; the page redraws it at its real width). Pointing at it shows
	// the nearest season's rank.
	let { points, name }: { points: ChartPoint[]; name: string } = $props();
	let width = $state(640);
	const c = $derived(chartLayout(points, width));
	const few = $derived(points.length <= 8);

	let at = $state<number | null>(null);
	let tip = $state<HTMLElement>();
	function show(e: PointerEvent) {
		const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
		const px = ((e.clientX - rect.left) / rect.width) * (c.W - c.L - c.R) + c.L;
		let i = 0;
		points.forEach((_, j) => { if (Math.abs(c.x(j) - px) < Math.abs(c.x(i) - px)) i = j; });
		at = i;
	}
	// the tip sits over its point, kept inside the box
	$effect(() => {
		if (at == null || !tip) return;
		const cx = c.x(at), cy = c.y(points[at].v), tw = tip.offsetWidth;
		tip.style.left = `${Math.min(Math.max(cx - tw / 2, 0), width - tw)}px`;
		tip.style.top = `${Math.max(0, cy - tip.offsetHeight - 12)}px`;
	});
</script>

<div class="chart-wrap" id="pl-chart" bind:clientWidth={width}>
	<svg viewBox="0 0 {c.W} {c.H}" height={c.H} role="img" aria-label="{name} rank, {Math.round(points[0].v)} to {Math.round(points[points.length - 1].v)}">
		<g class="chart-grid">{#each c.ticks as v (v)}<line x1={c.L} x2={c.W - c.R} y1={c.y(v).toFixed(1)} y2={c.y(v).toFixed(1)} />{/each}</g>
		<g class="chart-axis">
			{#each c.ticks as v (v)}<text x={c.L - 6} y={(c.y(v) + 3).toFixed(1)} text-anchor="end">{Math.round(v)}</text>{/each}
			{#each points as d, i (d.label)}{#if c.showLabel(i)}<text x={c.x(i).toFixed(1)} y={c.H - 6} text-anchor="middle">{d.label}</text>{/if}{/each}
		</g>
		<path class="chart-line" d={c.path} />
		{#if few}
			{#each points as d, i (d.label)}
				<circle class="season-dot" class:est={d.est} cx={c.x(i).toFixed(1)} cy={c.y(d.v).toFixed(1)} r="4.5" />
				<text class="season-label" x={c.x(i).toFixed(1)} y={(c.y(d.v) - 9).toFixed(1)} text-anchor="middle">{Math.round(d.v)}</text>
			{/each}
		{/if}
		{#if at != null}
			<line class="chart-cross" x1={c.x(at)} x2={c.x(at)} y1={c.T} y2={c.H - c.B} />
			<circle class="chart-dot" cx={c.x(at)} cy={c.y(points[at].v)} r="4.5" />
		{/if}
		<rect x={c.L} y="0" width={c.W - c.L - c.R} height={c.H} fill="transparent" role="presentation" onpointermove={show} onpointerdown={show} onpointerleave={() => (at = null)} />
	</svg>
	{#if at != null}<div class="chart-tip" bind:this={tip}>{points[at].season}<br />Rank <b>{points[at].v.toFixed(1)}</b>{#if points[at].est}<br />estimated{/if}</div>{/if}
</div>
