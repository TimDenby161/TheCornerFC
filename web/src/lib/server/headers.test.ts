import { describe, expect, it } from 'vitest';
import { SECURITY_HEADERS, secured } from './headers';

describe('the security headers', () => {
	it('are the four the security check found missing', () => {
		expect(Object.keys(SECURITY_HEADERS).sort()).toEqual(['permissions-policy', 'referrer-policy', 'strict-transport-security', 'x-content-type-options']);
		expect(SECURITY_HEADERS['strict-transport-security']).toMatch(/^max-age=31536000; includeSubDomains$/);
		expect(SECURITY_HEADERS['x-content-type-options']).toBe('nosniff');
	});
	it('go on a page without touching what it already says', async () => {
		const page = secured(new Response('<p>hi</p>', { status: 200, headers: { 'cache-control': 'public, max-age=60', vary: 'Cookie' } }));
		for (const [k, v] of Object.entries(SECURITY_HEADERS)) expect(page.headers.get(k)).toBe(v);
		expect(page.headers.get('cache-control')).toBe('public, max-age=60');
		expect(page.headers.get('vary')).toBe('Cookie');
		expect(page.status).toBe(200);
		expect(await page.text()).toBe('<p>hi</p>');
	});
	it('go on a redirect, whose own headers are fixed, as a new response to the same place', () => {
		const moved = secured(Response.redirect('https://thecornerfc.com/account', 303));
		expect(moved.status).toBe(303);
		expect(moved.headers.get('location')).toBe('https://thecornerfc.com/account');
		expect(moved.headers.get('strict-transport-security')).toBe(SECURITY_HEADERS['strict-transport-security']);
	});
});
