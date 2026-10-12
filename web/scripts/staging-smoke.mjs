// Is the staging site serving this commit, and is it really staging? Run by the Staging workflow
// on every push to the staging branch; a commit can be promoted to main only once this passes.
//
//   node web/scripts/staging-smoke.mjs <address> <commit>
//   STAGING_ACCESS_CLIENT_ID / STAGING_ACCESS_CLIENT_SECRET: the Cloudflare Access service token
//   WAIT_MINUTES: how long to wait for Cloudflare's build of this commit (default 15)
//
// It only reads. Every line it prints starts "ok" or "FAILED".
import { readFileSync } from 'node:fs';

const [base, commit] = [(process.argv[2] || '').replace(/\/$/, ''), process.argv[3] || ''];
if (!/^https:\/\//.test(base) || !/^[0-9a-f]{7,40}$/.test(commit)) { console.log('FAILED usage: staging-smoke.mjs https://address commit'); process.exit(2); }

// the two projects, as the site itself has them
const table = readFileSync(new URL('../src/lib/environments.ts', import.meta.url), 'utf8');
const project = (name) => new RegExp(`${name}: \\{\\s*project: '([a-z0-9]*)'`).exec(table)?.[1];
const production = project('production'), staging = project('staging');

const id = process.env.STAGING_ACCESS_CLIENT_ID, secret = process.env.STAGING_ACCESS_CLIENT_SECRET;
const token = id && secret ? { 'CF-Access-Client-Id': id, 'CF-Access-Client-Secret': secret } : {};
const get = (path, headers = token) => fetch(base + path, { headers, redirect: 'manual' });

let failed = 0;
const check = (what, passed, detail = '') => { console.log(`${passed ? 'ok' : 'FAILED'} ${what}${passed || !detail ? '' : `: ${detail}`}`); if (!passed) failed++; };

check('the two projects are recorded and differ', !!production && !!staging && production !== staging);
check('the check has its Access token', !!id && !!secret);
if (failed) process.exit(1);

// Cloudflare builds the same push: wait until the site answers with this commit
const until = Date.now() + Number(process.env.WAIT_MINUTES || 15) * 60_000;
let version = null, last = '';
while (Date.now() < until) {
	try {
		const r = await get('/version');
		last = `HTTP ${r.status}`;
		if (r.ok) { version = await r.json(); last = `commit ${String(version.commit).slice(0, 9)}`; if (version.commit === commit) break; }
	} catch (err) { last = String(err.message || err); }
	version = null;
	await new Promise((done) => setTimeout(done, 15_000));
}
check(`the site serves commit ${commit.slice(0, 9)}`, !!version, `last answer: ${last}`);
if (!version) process.exit(1);
check('it says it is staging', version.environment === 'staging', version.environment);
check('it reads the staging project', version.project === staging && version.project !== production);

// closed to the public: without the token, Access must not let the page through
const open = await get('/version', {});
check('without the Access token the site does not answer', open.status !== 200, `HTTP ${open.status}`);

// the pages answer (each reads the staging database on the server), say they are staging, are
// kept from search engines, and name production's project nowhere
for (const path of ['/', '/clubs', '/players', '/matches', '/stats', '/terms']) {
	const r = await get(path), body = await r.text();
	check(`${path} answers`, r.status === 200, `HTTP ${r.status}`);
	check(`${path} is marked not for search engines`, /noindex/.test(r.headers.get('x-robots-tag') || ''));
	check(`${path} names production's project nowhere`, !body.includes(production) && !(r.headers.get('content-security-policy') || '').includes(production));
	if (path === '/') check('the page carries the staging strip', body.includes('staging-strip'));
}
const robots = await (await get('/robots.txt')).text();
check('robots.txt keeps everything out', /^Disallow: \/$/m.test(robots));

console.log(failed ? `FAILED ${failed} check(s)` : 'ok staging is serving this commit');
process.exit(failed ? 1 : 0);
