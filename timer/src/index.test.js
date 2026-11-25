// node --test timer/src/  (no packages needed)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import timer, { JOBS, DAILY, dispatchRequest, workflowsFor } from './index.js';

const crons = JSON.parse(readFileSync(new URL('../wrangler.jsonc', import.meta.url), 'utf8')
	.replace(/^\s*\/\/.*$/gm, '')).triggers.crons;

test('every Cron Trigger starts a job, and every job has a trigger', () => {
	assert.deepEqual([...crons].sort(), Object.keys(JOBS).sort());
	assert.deepEqual(Object.values(JOBS).sort(), ['fpl.yml', 'matchday.yml', 'nightly.yml']);
});

test('a tick asks GitHub to run the workflow on main, marked as the timer', async () => {
	const r = dispatchRequest('matchday.yml', 'tok');
	assert.equal(r.method, 'POST');
	assert.equal(r.url, 'https://api.github.com/repos/TimDenby161/TheCornerFC/actions/workflows/matchday.yml/dispatches');
	assert.equal(r.headers.get('authorization'), 'Bearer tok');
	assert.equal(r.headers.get('content-type'), 'application/json');
	assert.deepEqual(await r.json(), { ref: 'main', inputs: { source: 'timer' } });
});

test('each tick sends one request for its own job, and nothing for an unknown one', async () => {
	const sent = [];
	const real = globalThis.fetch;
	globalThis.fetch = async (request) => { sent.push(request.url); return new Response(null, { status: 204 }); };
	try {
		await timer.scheduled({ cron: '17 1 * * *' }, { GITHUB_TOKEN: 't' });
		await timer.scheduled({ cron: '5 5 * * *' }, { GITHUB_TOKEN: 't' });
	} finally {
		globalThis.fetch = real;
	}
	assert.deepEqual(sent, ['https://api.github.com/repos/TimDenby161/TheCornerFC/actions/workflows/nightly.yml/dispatches']);
});

test('the 06:30 UTC half-hour tick also starts the morning email, and only that tick', async () => {
	assert.deepEqual(DAILY, { '06:30': 'daily-report.yml' });
	assert.deepEqual(workflowsFor('*/30 * * * *', new Date('2026-11-26T06:30:00Z')), ['matchday.yml', 'daily-report.yml']);
	assert.deepEqual(workflowsFor('*/30 * * * *', new Date('2026-11-26T07:00:00Z')), ['matchday.yml']);
	assert.deepEqual(workflowsFor('0 7,13,19 * * *', new Date('2026-11-26T06:30:00Z')), ['fpl.yml']);

	const sent = [];
	const real = globalThis.fetch;
	globalThis.fetch = async (request) => { sent.push(request.url.split('/workflows/')[1]); return new Response(null, { status: 204 }); };
	try {
		await timer.scheduled({ cron: '*/30 * * * *', scheduledTime: Date.parse('2026-11-26T06:30:00Z') }, { GITHUB_TOKEN: 't' });
	} finally {
		globalThis.fetch = real;
	}
	assert.deepEqual(sent, ['matchday.yml/dispatches', 'daily-report.yml/dispatches']);
});

test('it has nothing to visit', async () => {
	assert.equal((await timer.fetch()).status, 404);
});
