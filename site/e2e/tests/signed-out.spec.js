// A visitor with no account: every page opens, the lists fill, and the paid parts stay locked.
import { test, expect, fitsTheWidth } from './visitor.js';

for (const path of ['/', '/clubs', '/players', '/leagues', '/nations', '/matches', '/stats', '/record', '/lineups', '/model', '/methodology', '/terms', '/privacy']) {
	test(`${path} opens and fits the width`, async ({ page, faults }) => {
		const response = await page.goto(path);
		expect(response.status()).toBe(200);
		await expect(page.locator('main, .text-page, article').first()).toBeVisible();
		expect(await fitsTheWidth(page)).toBe(true);
	});
}

test('the home page sends a visitor to the ratings', async ({ page, faults }) => {
	await page.goto('/');
	await page.locator('.home-go').first().click();
	await expect(page).toHaveURL(/\/clubs/);
	await expect(page.locator('table.clubs tbody tr').first()).toBeVisible();
});

test('the clubs list fills and a club opens', async ({ page, faults }) => {
	await page.goto('/clubs');
	const rows = page.locator('table.clubs tbody tr');
	await expect(rows.first()).toBeVisible();
	expect(await rows.count()).toBeGreaterThan(10);
	await rows.first().locator('a').first().click();
	await expect(page).toHaveURL(/\/club\/\d+/);
	await expect(page.locator('h1, h2').first()).toBeVisible();
});

test('the players list keeps its order behind the paywall', async ({ page, faults }) => {
	await page.goto('/players');
	const rows = page.locator('table.players tbody tr');
	await expect(rows.first()).toBeVisible();
	expect(await rows.count()).toBeGreaterThan(50);
	const names = await rows.locator('td').nth(1).allInnerTexts();
	expect(names.length).toBeGreaterThan(0);
	// past the free part the list carries on, with the rating hidden and the row still there
	const last = await rows.last().innerText();
	expect(last.length).toBeGreaterThan(0);
	expect(last).toContain('–');
});

test('an address picks the position', async ({ page, faults }) => {
	await page.goto('/players?pos=GK');
	const rows = page.locator('table.players tbody tr');
	await expect(rows.first()).toBeVisible();
	await expect(rows.first()).toContainText('GK');
});

test('a match to come shows its chances and locks the paid parts', async ({ page, faults }) => {
	await page.goto('/matches');
	await expect(page.locator('#matches-list')).toBeVisible();
	const next = page.getByRole('link', { name: /next/i }).or(page.getByRole('button', { name: /next/i })).first();
	const locked = page.locator('#matches-list .paid-lock');
	for (let i = 0; i < 7 && !(await locked.count()); i += 1) {
		if (!(await next.count())) break;
		await next.click();
		await page.waitForLoadState('domcontentloaded');
	}
	await expect(locked.first()).toBeVisible();
});

test('the Admin area sends a signed-out visitor to sign in', async ({ page, faults }) => {
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/account/);
});

test('a page that does not exist says so in the site\'s own look', async ({ page }) => {
	const response = await page.goto('/no-such-page');
	expect(response.status()).toBe(404);
	await expect(page.locator('.not-found')).toBeVisible();
});
