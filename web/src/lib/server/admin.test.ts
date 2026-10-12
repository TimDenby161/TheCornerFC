import { isHttpError } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';
import { adminDoc, adminGate, isAdmin, isAdminPath } from './admin';

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type F = typeof globalThis.fetch;
const sent = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map(([url, init]) => ({ url: String(url), headers: (init?.headers || {}) as Record<string, string>, body: init?.body as string }));
const refused = async (run: () => Promise<unknown>) => { try { await run(); } catch (e) { return isHttpError(e) ? e.status : String(e); } return 'answered'; };

describe('the Admin gate', () => {
	it('covers /admin and everything under it, and nothing else', () => {
		for (const p of ['/admin', '/admin/', '/admin/changes', '/admin/changes/MC-0001', '/admin/simulation/__data.json', '/admin/anything/added/later']) expect(isAdminPath(p)).toBe(true);
		for (const p of ['/', '/administrator', '/admins', '/clubs', '/account', '/simulation', '/stats/admin']) expect(isAdminPath(p)).toBe(false);
	});
	it('leaves every other page alone without asking the database', async () => {
		const fetch = vi.fn(async () => answer(true));
		expect(await adminGate(fetch as unknown as F, '/clubs', 'tok')).toBe('open');
		expect(await adminGate(fetch as unknown as F, '/', undefined)).toBe('open');
		expect(fetch).not.toHaveBeenCalled();
	});
	it('sends a visitor who is not signed in to sign in, without asking the database', async () => {
		const fetch = vi.fn(async () => answer(true));
		expect(await adminGate(fetch as unknown as F, '/admin/simulation', undefined)).toBe('signin');
		expect(await adminGate(fetch as unknown as F, '/admin/changes/__data.json', '')).toBe('signin');
		expect(fetch).not.toHaveBeenCalled();
	});
	it('lets in only the visitor the database says is an administrator', async () => {
		const yes = vi.fn(async () => answer(true)), no = vi.fn(async () => answer(false));
		expect(await adminGate(yes as unknown as F, '/admin/changes', 'tok-admin')).toBe('admin');
		expect(await adminGate(no as unknown as F, '/admin/changes', 'tok-visitor')).toBe('refuse');
		expect(sent(yes)[0].url).toMatch(/\/rest\/v1\/rpc\/am_admin$/);
		expect(sent(yes)[0].headers.Authorization).toBe('Bearer tok-admin');
	});
	it('refuses when the database gives anything but a plain yes, or can\'t be reached', async () => {
		for (const body of [null, 'true', 1, { ok: true }, []]) expect(await isAdmin(vi.fn(async () => answer(body)) as unknown as F, 'tok')).toBe(false);
		expect(await isAdmin(vi.fn(async () => answer({ message: 'permission denied' }, 403)) as unknown as F, 'tok')).toBe(false);
		expect(await isAdmin(vi.fn(async () => { throw new Error('offline'); }) as unknown as F, 'tok')).toBe(false);
		expect(await adminGate(vi.fn(async () => answer({}, 401)) as unknown as F, '/admin', 'expired')).toBe('refuse');
	});
});

describe("the administrator's documents", () => {
	it('are asked for with the visitor\'s own token, never without one', async () => {
		const fetch = vi.fn(async () => answer({ ok: true, doc: { bets: [1] } }));
		expect(await adminDoc(fetch as unknown as F, 'tok-admin', 'bets')).toEqual({ bets: [1] });
		expect(sent(fetch)[0].url).toMatch(/\/rest\/v1\/rpc\/admin_doc$/);
		expect(sent(fetch)[0].headers.Authorization).toBe('Bearer tok-admin');
		expect(sent(fetch)[0].body).toBe('{"p_name":"bets"}');
		const none = vi.fn(async () => answer({ ok: true, doc: { bets: [1] } }));
		expect(await refused(() => adminDoc(none as unknown as F, undefined, 'bets'))).toBe(404);
		expect(none).not.toHaveBeenCalled();
	});
	it('are a page that isn\'t there for anyone the database refuses, whatever else it sends', async () => {
		for (const body of [{ ok: false }, { ok: false, doc: { bets: [1] } }, { doc: { bets: [1] } }, null, { ok: 'true', doc: {} }]) {
			expect(await refused(() => adminDoc(vi.fn(async () => answer(body)) as unknown as F, 'tok-visitor', 'bets'))).toBe(404);
		}
	});
	it('are null, not an error, before the export has stored one', async () => {
		expect(await adminDoc(vi.fn(async () => answer({ ok: true, doc: null })) as unknown as F, 'tok-admin', 'model_changes')).toBeNull();
	});
	it('are never kept between requests', async () => {
		const fetch = vi.fn(async () => answer({ ok: true, doc: {} }));
		await adminDoc(fetch as unknown as F, 'tok-admin', 'bets');
		await adminDoc(fetch as unknown as F, 'tok-admin', 'bets');
		expect(fetch).toHaveBeenCalledTimes(2);
	});
});

// The code itself: the paper bets are read in one way only, and nothing under /admin shares answers
const SOURCE = import.meta.glob(['/src/**/*.ts', '/src/**/*.svelte', '!/src/**/*.test.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const paths = Object.keys(SOURCE);
describe('the code', () => {
	it('reads the paper bets only as an administrator\'s document', () => {
		expect(paths.length).toBeGreaterThan(100);
		expect(paths.filter((p) => /(keptDoc|siteDoc|keptDocOrNull)(<[^>]*>)?\([^)]*'bets'/.test(SOURCE[p]))).toEqual([]);
		const readers = paths.filter((p) => /adminDoc(<[^>]*>)?\(/.test(SOURCE[p]) && p !== '/src/lib/server/admin.ts');
		expect(readers.length).toBeGreaterThan(0);
		for (const p of readers) expect(p.startsWith('/src/routes/(app)/admin/') || p === '/src/lib/server/changes.ts', p).toBe(true);
	});
	it('has the two betting pages under /admin and nowhere else', () => {
		const routes = paths.filter((p) => p.startsWith('/src/routes/'));
		expect(routes).toContain('/src/routes/(app)/admin/simulation/+page.server.ts');
		expect(routes).toContain('/src/routes/(app)/admin/model-vs-market/+page.server.ts');
		expect(routes.filter((p) => /(simulation|model-vs-market)/.test(p) && !p.startsWith('/src/routes/(app)/admin/'))).toEqual([]);
	});
	it('checks the gate in the hook, before any page or endpoint runs', () => {
		const hook = SOURCE['/src/hooks.server.ts'];
		expect(hook.indexOf('adminGate(')).toBeGreaterThan(0);
		expect(hook.indexOf('adminGate(')).toBeLessThan(hook.indexOf('await resolve(event'));
		expect(hook).toMatch(/gate === 'refuse'\) error\(404/);
		expect(hook).toMatch(/gate === 'signin'\) redirect\(303, '\/account'\)/);
	});
	it('holds no key that could read the documents without a visitor\'s token', () => {
		for (const p of paths) expect(/service_role|SERVICE_ROLE/.test(SOURCE[p]), p).toBe(false);
	});
	it('keeps the Admin area from search engines', () => {
		expect(SOURCE['/src/routes/robots.txt/+server.ts']).toContain("'Disallow: /admin'");
	});
});
