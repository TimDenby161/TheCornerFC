// What every test shares: the Access token, sent to the site's own address and nowhere else, and
// a watch for page errors. Cloudflare's analytics is blocked away from the real address, so it's
// not a fault.
import { test as base, expect } from '@playwright/test';

const id = process.env.STAGING_ACCESS_CLIENT_ID, secret = process.env.STAGING_ACCESS_CLIENT_SECRET;

export const test = base.extend({
	context: async ({ context, baseURL }, use) => {
		if (id && secret) {
			const host = new URL(baseURL).host;
			await context.route((url) => url.host === host, (route) => route.continue({
				headers: { ...route.request().headers(), 'CF-Access-Client-Id': id, 'CF-Access-Client-Secret': secret },
			}));
		}
		await use(context);
	},
	faults: async ({ page }, use) => {
		const faults = [];
		page.on('pageerror', (err) => faults.push(String(err)));
		page.on('console', (m) => { if (m.type() === 'error' && !/cloudflareinsights|ERR_FAILED|ERR_BLOCKED/.test(m.text())) faults.push(m.text()); });
		await use(faults);
		expect(faults, 'nothing goes wrong in the page').toEqual([]);
	},
});
export { expect };

// the page never scrolls sideways on its own, whatever is on it
export const fitsTheWidth = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
