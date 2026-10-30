// axe's serious and critical findings on the pages most visitors see.
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from './visitor.js';

for (const path of ['/', '/clubs', '/players', '/matches', '/stats', '/model', '/methodology']) {
	test(`${path} has no serious accessibility fault`, async ({ page }) => {
		await page.goto(path);
		await page.waitForLoadState('networkidle');
		const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
		const serious = violations.filter((v) => ['serious', 'critical'].includes(v.impact));
		expect(serious.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes[0].target}`)).toEqual([]);
	});
}
