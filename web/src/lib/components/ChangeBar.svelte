<script lang="ts">
	import { scale, type Tone } from '#lib/changes.ts';

	// A change in a measure as a bar from zero, with its interval as a whisker where it has one.
	// `reach` is the widest any bar beside it goes, so a column of them shares one scale. Left of
	// the line is a fall in the measure, which for these measures is the improvement.
	let { delta, interval = null, reach, tone, label, second = null }:
		{ delta: number | null; interval?: [number, number] | null; reach: number; tone: Tone | 'plain'; label: string; second?: number | null } = $props();
	const W = 220, H = 18, MID = W / 2;
	const x = $derived(scale([-reach, reach], [4, W - 4]));
</script>

<svg class="mc-bar" viewBox="0 0 {W} {H}" role="img" aria-label={label}>
	<line class="mc-zero" x1={MID} x2={MID} y1="1" y2={H - 1} />
	{#if delta != null}<rect class="mc-fill {tone}" x={Math.min(x(delta), MID).toFixed(1)} y={second != null ? 2 : 4} width={Math.max(Math.abs(x(delta) - MID), 1).toFixed(1)} height={second != null ? 6 : 10} />{/if}
	{#if second != null}<rect class="mc-fill second" x={Math.min(x(second), MID).toFixed(1)} y="10" width={Math.max(Math.abs(x(second) - MID), 1).toFixed(1)} height="6" />{/if}
	{#if interval}<line class="mc-whisker" x1={x(Math.max(interval[0], -reach)).toFixed(1)} x2={x(Math.min(interval[1], reach)).toFixed(1)} y1={H / 2} y2={H / 2} />{/if}
</svg>
