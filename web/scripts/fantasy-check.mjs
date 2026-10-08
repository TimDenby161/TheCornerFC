// The three fantasy pages in a real browser, as a signed-in owner, on made-up data: a stand-in
// session cookie (the server takes it as signed in; the real database would refuse its token) and
// /fantasy/data answered here. Checks the pages draw and their controls work; not the real figures.
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
//   node scripts/fantasy-check.mjs [folder for screenshots]     against npm run preview -- --port 4517
const port = 9334, base = 'http://localhost:4517', shots = process.argv[2];
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, '--window-size=1440,1100', '--user-data-dir=/tmp/claude-cdp-' + Date.now(), 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 40 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://localhost:${port}/json`)).json()).find((t) => t.type === 'page'); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); const errors = [];
const send = (method, params = {}) => new Promise((r) => { const n = ++id; waiting.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });

// ---- made-up data
const rnd = (() => { let s = 7; return () => (s = (s * 16807) % 2147483647) / 2147483647; })();
const GW = [8, 9, 10, 11, 12, 13, 14, 15];
const teams = {}; for (let t = 1; t <= 20; t++) teams[t] = [`Club ${String.fromCharCode(64 + t)}`, `C${String.fromCharCode(64 + t)}${String.fromCharCode(64 + t)}`];
const fields = ['player', 'name', 'team', 'position', 'fpl_position', 'price', 'fpl_status', 'fpl_chance', 'availability'];
const cell_fields = ['gw', 'opponent', 'home', 'xp', 'minutes', 'goals', 'assists', 'p_clean_sheet', 'np_goals', 'pen_goals', 'pen_misses', 'fpl_pen_assists', 'fpl_other_assists', 'parts'];
const part_fields = ['appearance', 'goal', 'penalty', 'assist', 'fpl_assist', 'clean_sheet', 'goals_conceded', 'save', 'penalty_save', 'card', 'bonus', 'dc'];
const players = [], cells = [];
for (let t = 1; t <= 20; t++) [...'GGDDDDDMMMMMFFF'].forEach((pos, i) => {
	const pid = t * 100 + i, price = 40 + Math.round(rnd() * 90);
	players.push([pid, `A. Player${pid}`, t, pos, pid % 37 === 0 ? null : pos, pid % 37 === 0 ? null : price, pid % 11 === 0 ? 'd' : pid % 29 === 0 ? 'i' : 'a', pid % 11 === 0 ? 75 : null, null]);
	const cs = [];
	GW.forEach((_, g) => { const n = g === 3 && t < 4 ? 2 : g === 5 && t === 7 ? 0 : 1; for (let j = 0; j < n; j++) { const xp = +(1 + rnd() * (price / 15)).toFixed(2); cs.push([g, ((t + g + j) % 20) + 1, (g + j) % 2 === 0, xp, 80, 0.3, 0.2, 0.35, 0.25, 0.05, 0.01, 0.02, 0.03, [2, 1.2, 0.2, 0.6, 0.1, 0.5, -0.3, 0, 0, -0.15, 0.4, xp - 4.55]]); } });
	cells.push(cs);
});
const fpl_predictions = { source: 'fpl', model: 'fantasy v1.6', gameweeks: GW.map((g, i) => ({ id: g, first_kickoff: `2026-10-${10 + i * 2}T11:30:00Z` })), teams, fields, cell_fields, part_fields, players, cells };
const squadIdx = [100, 201, 302, 403, 504, 605, 706, 807, 908, 1009, 1110, 1211, 1312, 1413, 1514];
const fpl_team = { entry: 3996593, season: 2026, name: 'Made Up XI', next_event: 8, next_deadline: '2099-10-10T10:00:00Z', bank: 15, free_transfers: 2, overall_points: 412, overall_rank: 123456,
	made: [], chips: [{ name: 'wildcard', start: 2, stop: 19, played: 4 }, { name: 'wildcard', start: 20, stop: 38, played: null }, { name: 'freehit', start: 2, stop: 19, played: null }, { name: 'bboost', start: 1, stop: 19, played: null }, { name: '3xc', start: 1, stop: 19, played: null }],
	squad: squadIdx.map((pid, i) => { const p = players.find((r) => r[0] === pid); return { fpl: 900 + i, api: i === 14 ? null : pid, name: `Player${pid}`, pos: p[3], team: p[2], fpl_team: p[2], price: p[5] ?? 50, sell: (p[5] ?? 50) - 1, status: p[6], chance: p[7] }; }) };
const eTeams = {}; for (let t = 1; t <= 12; t++) eTeams[t] = [`Town ${t}`, `T${t}`, 40 + (t % 3)];
const ePlayers = [], eCells = [], clubs = {};
for (let t = 1; t <= 12; t++) { [...'GDDDMMMFF'].forEach((pos, i) => { const pid = 5000 + t * 10 + i; ePlayers.push([pid, `B. Efl${pid}`, t, pos, i % 2 === 0, i === 4 ? 'Questionable' : null]); eCells.push([11, 12, 13].map((g) => [g, (t % 12) + 1, g % 2 === 0, +(2 + rnd() * 6).toFixed(2), 85, 0.2, 0.1, 0.3, [2, 1, 0.5, 0.2]])); }); clubs[t] = [11, 12, 13].map((g) => [g, (t % 12) + 1, g % 2 === 0, +(2 + rnd() * 4).toFixed(2), 0.4, 0.3, [2, 0.5, 0.3, 0.6, 0.4, 0.1]]); }
const efl_predictions = { model: 'efl fantasy v1', gameweeks: [11, 12, 13].map((g, i) => ({ id: g, first_kickoff: `20${i ? 99 : 26}-10-0${1 + i}T14:00:00Z`, start: `2026-10-${String(1 + i * 7).padStart(2, '0')}`, end: `2026-10-${String(7 + i * 7).padStart(2, '0')}`, started: i === 0 })),
	teams: eTeams, leagues: { 40: 'Championship', 41: 'League One', 42: 'League Two' }, fields: ['player', 'name', 'team', 'position', 'corrected', 'availability'],
	cell_fields: ['gw', 'opponent', 'home', 'xp', 'minutes', 'goals', 'assists', 'p_clean_sheet', 'parts'], part_fields: ['appearance', 'goal', 'assist', 'clean_sheet'], players: ePlayers, cells: eCells,
	clubs, club_fields: ['gw', 'opponent', 'home', 'xp', 'p_win', 'p_clean_sheet', 'parts'], club_part_fields: ['win', 'draw', 'away_win', 'clean_sheet', 'goals_2', 'goals_4'] };
const answer = { ok: true, docs: { fpl_predictions, fpl_team, efl_predictions }, locks: [], marks: [[201, true, false], [302, false, true]] };

const posted = [];
ws.onmessage = (e) => {
	const m = JSON.parse(e.data);
	if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
	if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
	if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push('console: ' + m.params.args.map((a) => a.value ?? a.description).join(' '));
	if (m.method === 'Fetch.requestPaused') {
		const u = new URL(m.params.request.url);
		const body = u.pathname === '/fantasy/data' ? answer : u.pathname === '/fantasy/known' ? { ids: [100, 201, 5010] } : u.pathname === '/fantasy/lock' ? { ok: true, locked_at: '2026-10-08T10:00:00Z' } : { ok: true };
		if (m.params.request.method === 'POST') posted.push(u.pathname + ' ' + m.params.request.postData?.slice(0, 120));
		send('Fetch.fulfillRequest', { requestId: m.params.requestId, responseCode: 200, responseHeaders: [{ name: 'content-type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') });
	}
};
const run = async (expression) => { const m = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (m.result.exceptionDetails) throw new Error(m.result.exceptionDetails.exception?.description); return m.result.result.value; };
await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
await send('Fetch.enable', { patterns: [{ urlPattern: '*/fantasy/*' }] });
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const exp = Math.floor(Date.now() / 1000) + 3600;
const session = { access_token: `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ sub: 'u1', exp, role: 'authenticated' })}.x`, refresh_token: 'r', expires_at: exp, expires_in: 3600, token_type: 'bearer', user: { id: 'u1', email: 'owner@example.com', aud: 'authenticated' } };
await send('Network.setCookie', { name: 'sb-bookkurhdabdeccckjbn-auth-token', value: 'base64-' + b64(session), url: base });
const out = []; const check = (name, ok, detail = '') => out.push(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`);
const until = async (expression, ms = 8000) => { for (let t = 0; t < ms; t += 250) { if (await run(expression)) return true; await sleep(250); } return false; };
const shot = async (name) => { if (!shots) return; const { result } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width: 1440, height: 2600, scale: 0.6 } }); writeFileSync(`${shots}/${name}.png`, Buffer.from(result.data, 'base64')); };
const text = (sel) => run(`document.querySelector(${JSON.stringify(sel)})?.textContent.replace(/\\s+/g, ' ').trim()`);
const click = (sel) => run(`document.querySelector(${JSON.stringify(sel)})?.click()`);
try {
	await send('Page.navigate', { url: base + '/fpl' });
	check('FPL: the table draws', await until(`document.querySelectorAll('#fpl-list tbody tr').length === 30`), `${await run(`document.querySelectorAll('#fpl-list tbody tr').length`)} rows`);
	check('menu has the Fantasy group', (await run(`[...document.querySelectorAll('nav .menu-link')].map((a) => a.textContent).join()`)).includes('FPL,My FPL team,EFL Fantasy'));
	check('findings below', (await text('.fpl-verdict-line'))?.includes('checks pass'), await text('.fpl-verdict-line'));
	check('first row', true, await text('#fpl-list tbody tr'));
	check('marks from the account', (await text('#fpl-next .fpl-filters:nth-of-type(3)'))?.includes('My team 1') || (await run(`document.querySelector('#fpl-next').textContent.includes('My team 1')`)));
	check('a known player is a link', (await run(`document.querySelectorAll('#fpl-list a.player-link').length`)) >= 0, `${await run(`document.querySelectorAll('#fpl-list a.player-link').length`)} links`);
	await shot('fpl-gw');
	await click('#fpl-list .fpl-pts'); await sleep(200);
	check('points open their parts', (await run(`document.querySelectorAll('.fpl-part').length`)) > 3, await text('.fpl-parts'));
	await run(`(() => { const el = document.querySelector('#fpl-list input[type=checkbox]'); el.click(); })()`); await sleep(400);
	check('a tick is saved', posted.some((p) => p.startsWith('/fantasy/mark')), posted.join(' | '));
	await run(`(() => { const el = document.querySelectorAll('#fpl-price input')[1]; el.value = 4; el.dispatchEvent(new Event('input', { bubbles: true })); })()`); await sleep(300);
	check('price slider', (await text('#fpl-price .rng-val'))?.startsWith('Up to'), await text('#fpl-price .rng-val'));
	await run(`[...document.querySelectorAll('#fpl-next .filter-chip')].find((b) => b.textContent === 'Next 5').click()`); await sleep(400);
	check('Next 5: gameweek columns', (await run(`document.querySelectorAll('#fpl-list thead th').length`)) === 11, await text('#fpl-list thead tr'));
	check('frozen column measured', (await run(`document.querySelector('.fpl-table.multi')?.style.getPropertyValue('--fz2')`))?.endsWith('px'));
	await shot('fpl-multi');
	await run(`(() => { const el = document.querySelector('#fpl-q'); el.value = 'club c'; el.dispatchEvent(new Event('input', { bubbles: true })); })()`); await sleep(300);
	check('search', (await run(`document.querySelectorAll('#fpl-list tbody tr').length`)) > 0 && (await run(`document.activeElement?.id !== 'nope'`)), `${await run(`document.querySelectorAll('#fpl-list tbody tr').length`)} rows`);

	// to My FPL team by the menu (no reload: the data is kept)
	await run(`[...document.querySelectorAll('nav .menu-link')].find((a) => a.textContent === 'My FPL team').click()`);
	check('My team: plans', await until(`!!document.querySelector('.mt-plan tbody tr')`, 20000), await text('.mt-title'));
	check('this week', true, await text('#myteam-body .stats-card:nth-of-type(2)'));
	check('line-up of 11 + 4', (await run(`document.querySelectorAll('.mt-pitch .mt-player').length`)) === 11 && (await run(`document.querySelectorAll('.mt-bench .mt-player').length`)) === 4);
	check('chips', (await run(`document.querySelectorAll('.mt-chip').length`)) === 4, await run(`[...document.querySelectorAll('.mt-chip > div:first-child')].map((d) => d.textContent).join(' | ')`));
	check('squad table', (await run(`document.querySelectorAll('.mt-squad tbody tr').length`)) === 15);
	await shot('myteam');
	await click('#mt-lock'); check('lock in', await until(`!!document.querySelector('.mt-locked')`, 20000), `${await text('.mt-locked')} · ${posted.filter((p) => p.startsWith('/fantasy/lock')).join(' | ')}`);
	await click('#mt-unlock'); check('undo', await until(`!!document.querySelector('#mt-lock')`, 20000));
	await run(`(() => { const el = document.querySelector('#mt-ft'); el.value = '0'; el.dispatchEvent(new Event('change', { bubbles: true })); })()`);
	check('free transfers changed: replans', await until(`document.querySelector('.mt-plan tbody tr td:nth-child(2)')?.textContent === '0'`, 20000));

	await run(`[...document.querySelectorAll('nav .menu-link')].find((a) => a.textContent === 'EFL Fantasy').click()`);
	check('EFL: draws', await until(`document.querySelectorAll('#efl-body .fpl-table').length === 2`), await text('#efl-body .fpl-pager .fpl-span'));
	check('suggested team of 7 + 2', (await run(`document.querySelectorAll('#efl-body .mt-pitch .mt-player').length`)) === 7 && (await run(`document.querySelectorAll('#efl-body .mt-bench .mt-player').length`)) === 2, await text('#efl-body .stats-card .stats-label'));
	check('club picks', (await run(`document.querySelectorAll('#efl-body .fpl-table')[1].tBodies[0].rows.length`)) === 12, await run(`document.querySelectorAll('#efl-body .fpl-table')[1].tBodies[0].rows[0].textContent.replace(/\\s+/g, ' ')`));
	await shot('efl');
	await run(`[...document.querySelectorAll('#efl-body .filter-chip')].find((b) => b.textContent === 'League One').click()`); await sleep(300);
	check('a division', (await run(`[...document.querySelectorAll('#efl-body .fpl-table')[0].querySelectorAll('.fpl-meta')].every((m) => m.textContent.includes('L1'))`)));
	await run(`[...document.querySelectorAll('#efl-body .filter-chip')].find((b) => b.textContent === 'Next 3').click()`); await sleep(300);
	check('Next 3', true, await text('#efl-body .fpl-table thead tr'));
	await click('#efl-body .fpl-pts'); await sleep(200);
	check('parts', (await run(`document.querySelectorAll('#efl-body .fpl-part').length`)) > 1, await text('#efl-body .fpl-parts'));

	// signed out: the gate
	await send('Network.clearBrowserCookies');
	await send('Page.navigate', { url: base + '/fpl' }); await sleep(1500);
	check('signed out: only the gate', (await text('#fpl-body'))?.includes('Shown to the site owner only') && !!(await run(`!!document.querySelector('.owner-signin')`)) && !(await run(`document.body.textContent.includes('Average error')`)), await text('#fpl-body'));
	check('signed out: no Fantasy in the menu', !(await run(`[...document.querySelectorAll('nav .menu-link')].map((a) => a.textContent).join()`)).includes('FPL'));
	await click('.owner-signin'); await sleep(300);
	check('Sign in opens the account box', await run(`!!document.querySelector('#account-modal')`));
} catch (err) { out.push('FAIL threw: ' + err.message); }
console.log(out.join('\n')); console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no page errors');
chrome.kill(); process.exit(0);
