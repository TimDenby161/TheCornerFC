import { isHttpError } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';
import type { ChangesDoc } from '#lib/changes.ts';
import { load as list } from '../../routes/(app)/admin/changes/+page.server.ts';
import { load as one } from '../../routes/(app)/admin/changes/[id]/+page.server.ts';

// The two pages' server code on a small record, with the database stood in for
const expected = (delta?: number) => ({ improves: null, metrics: delta == null ? [] : [{ metric: 'log_loss', delta, source: 'DESIGN.md' }], betting: null, confidence: null, evidence: null });
const base = { recorded: '2026-10-13', retrospective: true, component: 'Match probabilities', model: 'match', what: 'w', why: 'y', how: 'h', hypothesis: 'hyp', success_criteria: 'bar',
	code: { commit: null, experiment: 'experiments/x', model_version: null }, recorded_at: '2026-10-14T01:20:00+00:00', deployed_day_known: null, reverted_on: null, decided_on: '2026-10-12', forward: null };
const tested = { type: 'result' as const, date: '2026-10-12', evaluation: 'backtest' as const, unseen: 'partly' as const, label: 'Test', metric: 'log_loss', delta: -0.00076, n: 44383, period: ['2024-07-01', '2026-10-11'] as [string, string],
	baseline: 0.9936, after: 0.99284, interval: [-0.00115, -0.00039] as [number, number], interval_level: 0.95, vs_market: null, meaningful: 'Small', source: 'experiments/x/REPORT.md', experimental: true };
const doc: ChangesDoc = {
	generated_at: '2026-10-14T01:20:00+00:00', environment: 'staging', stored: true, differs: [], not_specified: 'Not specified',
	statuses: ['Proposed', 'Testing', 'Accepted', 'Rejected', 'Reverted', 'Inconclusive'], components: ['Club rank', 'Match probabilities'],
	current: { version: 'match-prediction', versions: [{ name: 'match-prediction', n: 740 }], n: 740, period: { from: '2026-09-26T12:00:00+00:00', to: '2026-10-11T19:00:00+00:00' }, log_loss: 0.9867, brier: 0.5885, accuracy: 0.523, vs_market: { n: 1147, model_log_loss: 0.9739, market_log_loss: 0.9536 } },
	series: [{ month: '2026-10', source: 'live', n: 700, log_loss: 0.975, brier: 0.58 }],
	changes: [
		{ ...base, id: 'MC-0001', title: 'Sharpening', date: '2026-10-12', kind: 'experiment', expected: expected(-0.0007), status: 'Rejected', stage: 'Tested and rejected', deployed: false, deployed_on: null,
			events: [tested, { type: 'decision', date: '2026-10-12', status: 'Rejected', reason: 'Below the bar' }], results: [tested] },
		{ ...base, id: 'MC-0002', title: 'Home edge', date: '2026-09-01', kind: 'production change', component: 'Club rank', expected: expected(), status: 'Accepted', stage: 'Deployed to production', deployed: true, deployed_on: '2026-09-01', deployed_day_known: false,
			events: [{ type: 'deployed', date: '2026-09-01', date_known_to: 'month', commit: null }], results: [{ ...tested, delta: -0.00113, interval: null, interval_level: null }],
			forward: { from: null, to: null, after: null, before: null, verdict: 'Cannot be judged', why: 'The day it went live was not recorded.', deployed_with: [] } }
	]
};
// (the live record is a second document; here the database has none stored)
const database = (answer: unknown) => vi.fn(async (_url: unknown, init?: RequestInit) => new Response(JSON.stringify(
	String(init?.body).includes('live_tracking') && (answer as { ok?: boolean })?.ok ? { ok: true, doc: null } : answer))) as unknown as typeof fetch;
const event = (answer: unknown, search = '', token = 'tok-admin', id = '') => ({ fetch: database(answer), locals: { token }, url: new URL(`https://x/admin/changes${search}`), params: { id } }) as never;
const status = async (run: () => Promise<unknown>) => { try { await run(); } catch (e) { return isHttpError(e) ? e.status : String(e); } return 200; };

describe('the Model Change Tracker', () => {
	it('gives the eight figures, the charts and the list for an administrator', async () => {
		const d = await list(event({ ok: true, doc }));
		if (!d.ready) throw new Error('not ready');
		expect(d.tiles.map((t) => t.label)).toEqual(['Production model', 'Log loss · Brier now', 'Right result now', 'Against guessing the base rates', 'Against the bookmakers',
			'Gained since the earliest dated version', 'Best proven gain not yet in production', 'Matches in the latest evaluation']);
		expect(d.tiles.map((t) => t.value)).toEqual(['match-prediction', '0.9867 · 0.5885', '52.3%', 'Not recorded', '+0.0203', '+0.00113', 'None yet', '740']);
		expect(d.tiles.some((t) => /^(Accepted|Rejected)/.test(t.label))).toBe(false);
		expect(d.tiles[0].note).toBe('2 changes proposed · 1 in production · 0 being tested');
		expect(d.rows.map((r) => [r.id, r.stage, r.expected, r.result?.word])).toEqual([['MC-0001', 'Tested and rejected', '−0.00070', 'Proven, not ready'], ['MC-0002', 'Deployed to production', 'Not specified', 'Unclear']]);
		expect(d.rows.map((r) => r.result?.mark)).toEqual(['none', 'none']);                 // a rejected gain and an unproven one: no green
		expect(d.deltas.find((x) => x.id === 'MC-0001')?.expected).toBe(0.0007);   // written down before the test, shown beside its result
		expect(d.steps.map((s) => s.id)).toEqual(['MC-0002']);       // the experiment is never in the production total
		expect(d.environment).toBe('staging');
	});
	it('narrows to the choices in the address', async () => {
		const d = await list(event({ ok: true, doc }, '?status=Rejected&component=Match%20probabilities'));
		if (!d.ready) throw new Error('not ready');
		expect(d.rows.map((r) => r.id)).toEqual(['MC-0001']);
		expect(d.all).toBe(2);
	});
	it('says so before the first record is stored, and is a missing page for anyone else', async () => {
		expect((await list(event({ ok: true, doc: null }))).ready).toBe(false);
		expect(await status(() => list(event({ ok: false })))).toBe(404);
		expect(await status(() => list(event({ ok: true, doc }, '', '')))).toBe(404);        // no token: the database is never asked
	});
	it('opens one change in full, with Not specified where nothing was recorded', async () => {
		const d = await one(event({ ok: true, doc }, '', 'tok-admin', 'MC-0002'));
		expect([d.change.improves, d.change.betting, d.change.commit, d.change.expected]).toEqual(['Not specified', 'Not specified', 'Not specified', []]);
		expect(d.results[0]).toMatchObject({ delta: '−0.00113', interval: null, word: 'Unclear', market: 'Not measured against bookmakers' });
		expect(d.forward).toMatchObject({ verdict: 'Cannot be judged', expected: 'Not specified', backtest: '−0.00113', observed: null });
		expect(d.events[0]).toMatchObject({ month: true, type: 'deployed' });
		expect(d.live).toEqual([]);
		expect(d.tracking).toBeNull();
		expect(await status(() => one(event({ ok: true, doc }, '', 'tok-admin', 'MC-9999')))).toBe(404);
		expect(await status(() => one(event({ ok: false }, '', 'tok-visitor', 'MC-0001')))).toBe(404);
	});
});
