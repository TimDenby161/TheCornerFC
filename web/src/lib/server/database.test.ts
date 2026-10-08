import { describe, expect, it, vi } from 'vitest';
import { askAs, keptDocOrNull, siteDoc, DatabaseError } from './database';

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const calls = (f: ReturnType<typeof vi.fn>) => f.mock.calls.map(([url, init]) => ({ url: String(url), headers: (init?.headers || {}) as Record<string, string>, body: init?.body as string | undefined }));

describe('askAs', () => {
	it('sends a signed-in visitor\'s token, and asks afresh every time', async () => {
		const fetch = vi.fn(async () => answer({ rows: [] }));
		await askAs(fetch as unknown as typeof globalThis.fetch, 'tok-1', 'site_players', { p_limit: 1 });
		await askAs(fetch as unknown as typeof globalThis.fetch, 'tok-1', 'site_players', { p_limit: 1 });
		expect(fetch).toHaveBeenCalledTimes(2);
		expect(calls(fetch)[0].headers.Authorization).toBe('Bearer tok-1');
		expect(calls(fetch)[0].url).toMatch(/\/rest\/v1\/rpc\/site_players$/);
		expect(calls(fetch)[0].body).toBe('{"p_limit":1}');
	});
	it('keeps a signed-out visitor\'s answer, and sends no token', async () => {
		const fetch = vi.fn(async () => answer({ rows: [1] }));
		const a = await askAs(fetch as unknown as typeof globalThis.fetch, undefined, 'site_matches', { p_team: 777001 });
		const b = await askAs(fetch as unknown as typeof globalThis.fetch, undefined, 'site_matches', { p_team: 777001 });
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(a).toEqual(b);
		expect(calls(fetch)[0].headers.Authorization).toBeUndefined();
	});
	it('never gives a signed-out visitor an answer fetched with a token', async () => {
		const fetch = vi.fn(async (_url: unknown, init?: RequestInit) => answer({ paid: !!(init?.headers as Record<string, string>).Authorization }));
		const f = fetch as unknown as typeof globalThis.fetch;
		expect(await askAs(f, 'tok-2', 'site_next_xi', { p_team: 777002 })).toEqual({ paid: true });
		expect(await askAs(f, undefined, 'site_next_xi', { p_team: 777002 })).toEqual({ paid: false });
		expect(await askAs(f, 'tok-2', 'site_next_xi', { p_team: 777002 })).toEqual({ paid: true });
	});
});

describe('siteDoc', () => {
	it('treats a key with no row as not found', async () => {
		const f = vi.fn(async () => answer(null)) as unknown as typeof globalThis.fetch;
		await expect(siteDoc(f, 'clubs/1', 0)).rejects.toMatchObject({ missing: true, status: 404 });
		expect(await keptDocOrNull(f, 'clubs/777003')).toBeNull();
	});
	it('asks once more after a server error, then gives up', async () => {
		const f = vi.fn(async () => answer({}, 503));
		await expect(siteDoc(f as unknown as typeof globalThis.fetch, 'rankings', 0)).rejects.toBeInstanceOf(DatabaseError);
		expect(f).toHaveBeenCalledTimes(2);
	});
});
