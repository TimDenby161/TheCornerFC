// node --test timer/src/  (no packages needed)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import timer, { JOBS, dispatchRequest } from './index.js';

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

test('it has nothing to visit', async () => {
	assert.equal((await timer.fetch()).status, 404);
});
