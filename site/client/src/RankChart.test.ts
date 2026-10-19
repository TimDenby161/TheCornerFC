import { describe, expect, it } from 'vitest';
import { chartLayout } from '../../../web/src/lib/player.ts';

// The chart's layout comes from the Svelte site's own code (one copy until the switch-over): the
// React chart draws what it says, at the box's width
describe('the season rank chart', () => {
	const points = [{ label: '23/24', season: '2023/24', v: 61.2, est: false }, { label: '24/25', season: '2024/25', v: 70.4, est: true }, { label: '25/26', season: '2025/26', v: 74.9, est: false }];
	it('fits its width, never narrower than 260', () => {
		expect(chartLayout(points, 640).W).toBe(640);
		expect(chartLayout(points, 200).W).toBe(260);
	});
	it('starts its line at the first season and labels the last', () => {
		const c = chartLayout(points, 640);
		expect(c.path.startsWith(`M${c.x(0).toFixed(1)},`)).toBe(true);
		expect(c.showLabel(points.length - 1)).toBe(true);
	});
});
