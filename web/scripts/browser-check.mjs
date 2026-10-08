// A run-through of the pages in a real browser: headless Chrome, driven over its DevTools protocol
// (no test framework to install). It clicks, types and drags as a visitor would and checks what
// the page then shows and what its address says.
//   node scripts/browser-check.mjs [address]     default http://localhost:4517 (npm run preview -- --port 4517)
// It reads the live database through the app, so the names it expects are today's.
import { spawn } from 'node:child_process';
const port = 9333, base = (process.argv[2] || 'http://localhost:4517').replace(/\/$/, '');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, '--window-size=1440,900', '--user-data-dir=/tmp/claude-cdp-' + Date.now(), 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 40 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://localhost:${port}/json`)).json()).find((t) => t.type === 'page'); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); const errors = [];
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(m.params.entry.text + ' ' + (m.params.entry.url || '')); };
const send = (method, params = {}) => new Promise((r) => { const n = ++id; waiting.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
const run = async (expression) => { const m = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (m.result.exceptionDetails) throw new Error(m.result.exceptionDetails.exception?.description || 'eval failed'); return m.result.result.value; };
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
const open = async (path) => { await send('Page.navigate', { url: base + path }); await sleep(1800); };
const out = [];
const check = (name, ok, detail = '') => out.push(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`);
const rows = () => run(`document.querySelectorAll('table.players tbody tr').length`);
const first = () => run(`document.querySelector('table.players .pn-full')?.textContent`);

try {
await open('/players');
check('opens with 100 rows', (await rows()) === 100, await first());
// scroll the list's box to its foot: more rows arrive
await run(`(() => { const b = document.querySelector('.table-scroll'); b.scrollTop = b.scrollHeight; window.scrollTo(0, document.body.scrollHeight); })()`); await sleep(1800);
check('more rows on scroll', (await rows()) >= 200, `${await rows()} rows`);

// age slider: drag the upper handle down to 21
await run(`(() => { const el = document.querySelector('#age-max'); el.value = 5; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); })()`); await sleep(1500);
check('age slider writes the address', (await run('location.search')).includes('age=-21'), await run('location.search'));
check('age label follows', (await run(`document.querySelector('#age-filter .rng-val')?.textContent`)) === '16–21');
check('the list is the under-21s', (await first()) === 'Lamine Yamal' && (await run(`[...document.querySelectorAll('table.players tbody tr td.col-age')].every((td) => Number(td.textContent) <= 21)`)), `${await rows()} rows`);
check('menu count follows the age', Number(await run(`document.querySelector('#table-filters .menu-trigger .cnt')?.textContent`)) < 2000, await run(`document.querySelector('#table-filters .menu-trigger .cnt')?.textContent`));

// position: press ST on the pitch
await run(`document.querySelector('#pos-filter .pos[value="ST"]')?.click()`); await sleep(1500);
check('position pick in the address', (await run('location.search')).includes('pos=ST'), await run('location.search'));
check('"As ST" takes Ability\'s place', (await run(`document.querySelector('th.col-posrank')?.textContent.trim()`))?.startsWith('As ST'));

// club box: focus, the list loads, open the first league, pick its first club
await send('Emulation.setFocusEmulationEnabled', { enabled: true }); await run(`document.querySelector('#club-input').focus()`); await sleep(1800);
check('club list opens with leagues', (await run(`document.querySelectorAll('#club-menu .who-league').length`)) > 10, `${await run(`document.querySelectorAll('#club-menu .who-league').length`)} leagues`);
await run(`document.querySelector('#club-menu .who-league')?.click()`); await sleep(300);
const clubName = await run(`document.querySelector('#club-menu .who-opt:not(.who-league) .nm')?.textContent`);
await run(`document.querySelector('#club-menu .who-opt:not(.who-league)')?.click()`); await sleep(1500);
check('club pick in the address and as a chip', (await run('location.search')).includes('club=') && (await run(`document.querySelector('#who-chips .who-chip')?.textContent`))?.includes(clubName), `${clubName} · ${await run('location.search')}`);
check('list stays open for another pick', (await run(`document.querySelector('#club-menu').hidden`)) === false);
// type in the nationality box and press Enter on the best match
await run(`(() => { const el = document.querySelector('#nat-input'); el.focus(); el.value = 'engl'; el.dispatchEvent(new Event('input', { bubbles: true })); })()`); await sleep(400);
await run(`document.querySelector('#nat-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))`); await sleep(1500);
check('nationality typed and picked with Enter', decodeURIComponent(await run('location.search')).includes('nat=England'), decodeURIComponent(await run('location.search')));
// clear the picks
await run(`document.querySelector('#who-filter .pos-clear')?.click()`); await sleep(1200);
check('Clear drops both picks', !/club=|nat=/.test(await run('location.search')), await run('location.search'));

// search as typed
await open('/players');
await run(`(() => { const el = document.querySelector('#table-search'); el.focus(); el.value = 'haaland'; el.dispatchEvent(new Event('input', { bubbles: true })); })()`); await sleep(1500);
check('search narrows as typed', (await rows()) === 1 && (await first()) === 'E. Haaland', `${await rows()} rows`);
// the other seasons
await open('/players?c=39');
await run(`document.querySelector('.years-btn')?.click()`); await sleep(1500);
check('+ opens the other seasons', (await run(`document.querySelectorAll('table.players.years thead th').length`)) > 12, `${await run(`document.querySelectorAll('table.players thead th').length`)} columns`);
// a club row on Clubs opens its page
await open('/clubs?c=39');
await run(`document.querySelector('table.clubs tbody tr td:nth-child(4)')?.click()`); await sleep(1500);
check('a Clubs row opens the club page', /^\/club\/\d+$/.test(await run('location.pathname')), await run('location.pathname'));
check('kick-off shown in local time after loading', await run(`!!document.querySelector('time[datetime]')`));

} catch (err) { out.push('STOPPED: ' + err.message.split('\n')[0]); out.push('at ' + await run('location.href') + ' · body: ' + (await run('document.body.innerText.slice(0, 300)'))); }
console.log(out.join('\n'));
console.log(errors.length ? 'PAGE ERRORS:\n' + [...new Set(errors)].join('\n') : 'no page errors');
ws.close(); chrome.kill();
process.exit(out.some((l) => !l.startsWith('ok')) || errors.length ? 1 : 0);
