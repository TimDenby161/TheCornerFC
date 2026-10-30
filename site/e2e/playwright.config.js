// Drives the site as visitors do, on phone and desktop sizes, against any address. It is written
// for staging's data (England's four divisions), so nothing here names a club, player or figure.
//   BASE_URL                                     default http://127.0.0.1:5280
//   STAGING_ACCESS_CLIENT_ID / _SECRET           the Access token, when the address is behind Access
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: './tests',
	timeout: 45_000,
	expect: { timeout: 15_000 },
	workers: 2,
	retries: process.env.CI ? 1 : 0,
	reporter: [['list']],
	use: { baseURL: process.env.BASE_URL || 'http://127.0.0.1:5280', trace: 'off', screenshot: 'off' },
	projects: [
		{ name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } } },
		{ name: 'phone', use: { browserName: 'chromium', ...devices['Pixel 7'] } },
	],
});
