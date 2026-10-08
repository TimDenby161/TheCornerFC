// A run-through of the pages in a real browser: headless Chrome, driven over its DevTools protocol
// (no test framework to install). It clicks, types and drags as a visitor would and checks what
// the page then shows and what its address says.
//   CHROME_MAP='thecornerfc.com 104.21.21.76': send a host to an address, to reach it before its DNS has settled
//   node scripts/browser-check.mjs [address]     default http://localhost:4517 (npm run preview -- --port 4517)
// It reads the live database through the app, so the names it expects are today's.
import { spawn } from 'node:child_process';
const port = 9333, base = (process.argv[2] || 'http://localhost:4517').replace(/\/$/, '');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`, '--window-size=1440,900', ...(process.env.CHROME_MAP ? [`--host-resolver-rules=MAP ${process.env.CHROME_MAP}`] : []), '--user-data-dir=/tmp/claude-cdp-' + Date.now(), 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 40 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://localhost:${port}/json`)).json()).find((t) => t.type === 'page'); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); const errors = [];
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error' && !/account\?\/signin/.test(m.params.entry.url || '')) errors.push(m.params.entry.text + ' ' + (m.params.entry.url || '')); };
const send = (method, params = {}) => new Promise((r) => { const n = ++id; waiting.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
const run = async (expression) => { const m = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (m.result.exceptionDetails) throw new Error(m.result.exceptionDetails.exception?.description || 'eval failed'); return m.result.result.value; };
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
const open = async (path) => { await send('Page.navigate', { url: base + path }); await sleep(1800); };
const out = [];
const check = (name, ok, detail = '') => out.push(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`);
// wait for something to be so on the page (up to `ms`), in place of a fixed pause: a slow answer from
// the database then makes a step slower, not wrong
const until = async (expression, ms = 8000) => { for (let t = 0; t < ms; t += 250) { if (await run(expression)) return true; await sleep(250); } return false; };
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
await run(`(() => { const el = document.querySelector('#table-search'); el.focus(); el.value = 'haaland'; el.dispatchEvent(new Event('input', { bubbles: true })); })()`); await until(`document.querySelectorAll('table.players tbody tr').length === 1`);
check('search narrows as typed', (await rows()) === 1 && (await first()) === 'E. Haaland', `${await rows()} rows`);
// a season's rank says his clubs that season when the pointer is on it (fetched on the first hover)
await open('/players?c=39');
await run(`document.querySelector('table.players tbody tr td.tip-cell').dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))`);
await until(`/ mins – /.test(document.querySelector('.col-tip')?.textContent || '')`);
check('season tip over a rank', /^Age \d+\n.+ – \d+\n[\d,]+ mins – \d+ G, \d+ A/.test(await run(`document.querySelector('.col-tip')?.textContent`)), JSON.stringify(await run(`document.querySelector('.col-tip')?.textContent`)));
// the other seasons
await open('/players?c=39');
await run(`document.querySelector('.years-btn')?.click()`); await until(`document.querySelectorAll('table.players.years thead th').length > 12`);
check('+ opens the other seasons', (await run(`document.querySelectorAll('table.players.years thead th').length`)) > 12, `${await run(`document.querySelectorAll('table.players thead th').length`)} columns`);
// a player's row opens his page; its tabs and the Stats switches are links
await open('/players?c=39');
await until(`!!document.querySelector('table.players tbody tr td:nth-child(3)')`);
await run(`document.querySelector('table.players tbody tr td:nth-child(3)')?.click()`); await until(`/^\\/player\\/\\d+$/.test(location.pathname) && !!document.querySelector('.page-tabs a')`);
check('a Players row opens the player page', /^\/player\/\d+$/.test(await run('location.pathname')), await run('location.pathname'));
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Stats')?.click()`); await sleep(1200);
await run(`[...document.querySelectorAll('.seg a')].find((a) => a.textContent === 'Per 90')?.click()`); await sleep(1200);
check('Stats tab, per 90', /\/stats$/.test(await run('location.pathname')) && (await run('location.search')) === '?per90=1' && /per 90 minutes/.test(await run(`document.querySelector('#pl-tab .page-note')?.textContent`)), await run('location.href'));
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Career')?.click()`); await sleep(1200);
check('Career chart drawn to its box', (await run(`document.querySelector('#pl-chart svg')?.getAttribute('viewBox')`)) !== '0 0 640 180' && (await run(`document.querySelectorAll('#pl-chart .season-dot').length`)) >= 2, await run(`document.querySelector('#pl-chart svg')?.getAttribute('viewBox')`));
// Home, the text pages, and links shared from the old site
await open('/');
await until(`document.querySelectorAll('.home-turn-list button').length >= 6`);
check('Home: a slide for each part of the site, the strongest clubs on the first', (await run(`document.querySelectorAll('.home-slide').length`)) >= 6 && (await run(`document.querySelectorAll('.home-slide .home-top')[0]?.children.length`)) === 7, `${await run(`document.querySelectorAll('.home-slide').length`)} slides`);
await run(`[...document.querySelectorAll('.home-turn-list button')].find((b) => b.textContent === 'Stats')?.click()`); await sleep(900);
check('picking a slide brings it up, and only it can be reached', (await run(`document.querySelector('.home-turn-list button[aria-current]')?.textContent`)) === 'Stats' && (await run(`[...document.querySelectorAll('.home-slide')].filter((s) => !s.inert).length`)) === 1);
await run(`document.querySelector('.home-close .home-ghost')?.click()`); await until(`location.pathname === '/methodology' && !!document.querySelector('.stat-v')`);
check('How the models work: the text page with its live figures, and no menu', (await run('location.pathname')) === '/methodology' && (await run(`document.querySelectorAll('.stat-v').length`)) >= 4 && !(await run(`!!document.querySelector('nav.tabs')`)), `${await run(`document.querySelectorAll('.stat-v').length`)} figures`);
await run(`document.querySelector('.back a')?.click()`); await until(`location.pathname === '/' && !!document.querySelector('nav.tabs')`);
check('its way back loads the site afresh, in the site\'s own look', (await run('location.pathname')) === '/' && (await run(`getComputedStyle(document.querySelector('nav.tabs')).display`)) === 'flex');
await open('/terms');
check('terms: the old site\'s text, its links pointing here', (await run(`document.querySelector('h1')?.textContent`)) === 'Terms of use' && (await run(`!!document.querySelector('a[href="/privacy#corrections"]')`)));
await open('/#/club/42/matches');
await until(`location.pathname === '/club/42/matches'`);
check('a link shared from the old site opens the same page here', (await run('location.pathname')) === '/club/42/matches' && (await run('location.hash')) === '', await run('location.href'));
await open('/clubs');
check('Clubs opens sorted by Current, as on the old site', (await run(`document.querySelector('table.clubs th.active')?.textContent.trim()`)) === 'Current' && (await run('location.search')) === '', await run(`document.querySelector('table.clubs tbody .team-link')?.textContent`));

// Matches: a day at a time, a round at a time for one competition
await open('/matches?d=2026-09-19');
const dayCards = await run(`document.querySelectorAll('#matches-list .match-card').length`);
check('a day\'s matches by competition', dayCards > 20 && (await run(`document.querySelectorAll('#matches-list .comp-group').length`)) > 5, `${dayCards} matches`);
check('finished matches carry a prediction rating', (await run(`document.querySelectorAll('#matches-list .rating-badge').length`)) > 5);
await run(`document.querySelector('#matches-list .comp-group-header')?.click()`); await sleep(300);
check('a competition folds away', await run(`document.querySelector('#matches-list .comp-group')?.classList.contains('collapsed')`));
await run(`document.querySelector('.secondary-filters a[aria-label="Next day"]')?.click()`); await sleep(1800);
check('the next day has its own address', (await run('location.search')) === '?d=2026-09-20', await run('location.search'));
await open('/matches?c=39&d=2026-09-19');
check('one competition goes a round at a time', /^Round 5/.test(await run(`document.querySelector('.secondary-filters select')?.selectedOptions[0]?.textContent`)) && (await run(`document.querySelectorAll('#matches-list .match-card').length`)) === 10, await run(`document.querySelector('.secondary-filters select')?.selectedOptions[0]?.textContent`));
// a finished match's card opens its line-ups (on a click anywhere on it) and its model detail
await run(`document.querySelector('#matches-list .match-card .match-score')?.click()`); await sleep(2500);
check('a card opens its line-ups: two elevens on pitches', (await run(`document.querySelectorAll('#matches-list .fixture-lineup-panel .pp-pitch').length`)) === 2 && (await run(`document.querySelectorAll('#matches-list .fixture-lineup-panel .xi-spot').length`)) === 22, `${await run(`document.querySelectorAll('#matches-list .fixture-lineup-panel .xi-spot').length`)} players`);
await run(`document.querySelectorAll('#matches-list .match-card')[1]?.querySelector('.why-toggle')?.click()`); await sleep(1800);
check('opening another card\'s model detail closes the first card', (await run(`document.querySelectorAll('#matches-list .fixture-lineup-panel').length`)) === 0 && (await run(`document.querySelectorAll('#matches-list .why-detail .why-sec').length`)) >= 2, `${await run(`document.querySelectorAll('#matches-list .why-detail .why-sec').length`)} sections`);
await run(`document.querySelector('.secondary-filters a.today-btn')?.click()`); await sleep(1800);
check('Next goes to the round to come, where the paid parts are locked', (await run('location.search')) === '?c=39' && (await run(`document.querySelectorAll('#matches-list .paid-lock').length`)) > 0);
await run(`document.querySelector('#matches-list .paid-lock .link-btn')?.click()`); await sleep(500);
check('"What subscribers get" opens the account box there', (await run(`document.querySelector('#account-title')?.textContent`)) === 'Subscribe');
await run(`document.querySelector('#account-modal .modal-close')?.click()`); await sleep(300);

// Leagues: the list, a league's page and its tabs, a country's page
await open('/leagues');
check('the leagues list, strongest first', (await run(`document.querySelectorAll('table.clubs tbody tr').length`)) > 30 && (await run(`document.querySelector('table.clubs tbody .team-link')?.textContent`)) === 'Premier League', await run(`document.querySelector('table.clubs tbody .team-link')?.textContent`));
await run(`document.querySelector('table.clubs tbody .team-link')?.click()`);
for (let i = 0; i < 20 && !/^\/league\/\d+\/table$/.test(await run('location.pathname')); i++) await sleep(300);
await sleep(600);
check('a league opens on its standings', (await run('location.pathname')) === '/league/39/table' && (await run(`document.querySelectorAll('table.league-table tbody tr').length`)) === 20);
await run(`[...document.querySelectorAll('table.league-table th.sortable a')].find((a) => a.textContent.trim() === 'GD')?.click()`); await sleep(1200);
const gdFirst = await run(`document.querySelector('table.league-table tbody .lt-gd')?.textContent`);
await run(`[...document.querySelectorAll('table.league-table th.sortable a')].find((a) => a.textContent.trim().startsWith('GD'))?.click()`); await sleep(1200);
check('a column sorts, and the other way on a second press', (await run('location.search')) === '?sort=gd&rev=1' && gdFirst !== (await run(`document.querySelector('table.league-table tbody .lt-gd')?.textContent`)), `${gdFirst} then ${await run(`document.querySelector('table.league-table tbody .lt-gd')?.textContent`)}`);
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Projected table')?.click()`); await sleep(1500);
check('the projected table\'s headline for a visitor who isn\'t a subscriber', (await run(`document.querySelectorAll('#league-tab table.league-table tbody tr').length`)) === 20 && /for subscribers/.test(await run(`document.querySelector('#league-tab .page-note')?.textContent`)));
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Matches')?.click()`); await sleep(1500);
const roundNow = await run(`document.querySelector('#round-select')?.value`);
await run(`document.querySelector('.round-nav a[aria-label="Previous round"]')?.click()`); await sleep(1500);
check('a league\'s matches step a round at a time', (await run(`document.querySelectorAll('.lf-row').length`)) === 10 && (await run(`document.querySelector('#round-select')?.value`)) !== roundNow && (await run('location.search')).startsWith('?round='), `${roundNow} -> ${await run(`document.querySelector('#round-select')?.value`)}`);
await run(`document.querySelector('.pl-hero .nat-link')?.click()`);
for (let i = 0; i < 20 && !/^\/country\//.test(await run('location.pathname')); i++) await sleep(300);
await sleep(600);
check('its country\'s page: leagues, cups and clubs', (await run('location.pathname')) === '/country/England' && (await run(`document.querySelectorAll('.lg-card').length`)) >= 10 && (await run(`document.querySelectorAll('#country-clubs tbody tr').length`)) === 50);

// Nations: the ranking, a nation's page and its tabs
await open('/nations');
check('the national team ranking', (await run(`document.querySelectorAll('#nations-body tbody tr').length`)) > 150);
await run(`[...document.querySelectorAll('#nations-body .filter-chip')].find((a) => a.textContent === 'CONMEBOL')?.click()`); await sleep(1500);
check('one confederation', (await run('location.search')) === '?c=CONMEBOL' && (await run(`document.querySelectorAll('#nations-body tbody tr').length`)) === 10, `${await run(`document.querySelectorAll('#nations-body tbody tr').length`)} nations`);
await open('/nation/England');
check('a nation\'s best players on a pitch, and every ranked player under it', (await run(`document.querySelectorAll('.dp-pitch .dp-row').length`)) > 20 && (await run(`document.querySelectorAll('#nat-tab .team-row').length`)) === 100, `${await run(`document.querySelectorAll('.dp-pitch .dp-row').length`)} on the pitch`);
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Predicted XI')?.click()`); await sleep(1800);
check('its predicted XI', (await run('location.pathname')) === '/nation/England/xi' && (await run(`document.querySelectorAll('#nat-tab .xi-spot').length`)) === 11);
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Formations')?.click()`); await sleep(1800);
await run(`document.querySelector('#nat-tab details.nat-match summary')?.click()`); await sleep(300);
check('formations, and a match opens to its starting XI', (await run(`document.querySelectorAll('#nat-tab .fm-card').length`)) >= 1 && (await run(`document.querySelectorAll('#nat-tab details[open] .nat-xi > span').length`)) === 11);
await run(`[...document.querySelectorAll('.page-tabs a')].find((a) => a.textContent === 'Players')?.click()`); await sleep(1800);
await run(`[...document.querySelectorAll('#nat-tab th.sortable a')].find((a) => a.textContent === 'G')?.click()`); await sleep(1500);
check('its players under the coach, sorted by goals', (await run('location.search')) === '?sort=goals' && Number(await run(`document.querySelector('#nat-tab tbody tr td:nth-child(6)')?.textContent`)) >= 3, `top scorer ${await run(`document.querySelector('#nat-tab tbody tr td:nth-child(6)')?.textContent`)}`);

// Stats and the Line-up record
await open('/stats');
const matches30 = await run(`document.querySelector('#stats-body .stats-value')?.textContent`);
await run(`[...document.querySelectorAll('#stats-ranges a')].find((a) => a.textContent === '12 months')?.click()`); await sleep(1500);
check('Stats: the range changes the figures', (await run('location.search')) === '?r=365d' && (await run(`document.querySelector('#stats-body .stats-value')?.textContent`)) !== matches30 && (await run(`document.querySelectorAll('#stats-body .calib-table').length`)) >= 2, `${matches30} -> ${await run(`document.querySelector('#stats-body .stats-value')?.textContent`)} matches`);
await run(`document.querySelector('#stats-filters button[value="c:England"]')?.click()`); await sleep(1500);
check('Stats: a country\'s competitions together, the range kept', (await run('location.search')).includes('r=365d') && decodeURIComponent(await run('location.search')).includes('c=c:England') && (await run(`document.querySelectorAll('#stats-body .stats-card').length`)) >= 8, decodeURIComponent(await run('location.search')));
await open('/lineups');
check('the line-up record saved before kick-off', (await run(`document.querySelectorAll('#lineup-body .stats-card').length`)) >= 10 && /of 11/.test(await run(`document.querySelectorAll('#lineup-body .stats-value')[1]?.textContent`)), await run(`document.querySelectorAll('#lineup-body .stats-value')[1]?.textContent`));
await run(`[...document.querySelectorAll('#lineup-source a')].find((a) => a.textContent === 'Reconstructed history')?.click()`);
for (let i = 0; i < 30 && (await run('location.search')) !== '?src=history'; i++) await sleep(400);
await sleep(1200);
check('the reconstructed history, with more to list', (await run('location.search')) === '?src=history' && /Reconstructed, not a live record/.test(await run(`document.querySelector('#lineup-body')?.textContent`)) && (await run(`!!document.querySelector('#lineup-body .lr-more')`)), `${await run(`document.querySelector('#lineup-body .stats-value')?.textContent`)} line-ups`);

// The two betting pages
await open('/model-vs-market');
check('Model vs Market: the three tiles, the 18+ note and the open selections', (await run(`document.querySelectorAll('#tips-top .kpi').length`)) === 3 && (await run(`!!document.querySelector('#tips-top .age-18')`)) && (await run(`document.querySelectorAll('#tips-body .tip-pick').length`)) > 0, `${await run(`document.querySelectorAll('#tips-body .tip-pick').length`)} selections`);
await run(`document.querySelector('#tips-body .tip-day')?.click()`); await sleep(300);
check('a day of selections folds away', await run(`document.querySelector('#tips-body .tip-day-body')?.classList.contains('collapsed')`));
await open('/simulation');
const settledAll = await run(`document.querySelectorAll('#bets-body .bet-row').length`);
await run(`[...document.querySelectorAll('#bet-market a')].find((a) => a.textContent === 'Result')?.click()`); await until(`location.search === '?m=1X2'`); await sleep(500);
check('Paper Simulation: a market narrows the record', settledAll > 50 && (await run(`document.querySelectorAll('#bets-body .bet-row').length`)) < settledAll && (await run(`!!document.querySelector('#bets-body .age-18')`)), `${settledAll} -> ${await run(`document.querySelectorAll('#bets-body .bet-row').length`)} settled`);
await run(`document.querySelector('#bets-body .calib-table tbody .team-link')?.click()`); await until(`/c=\\d+/.test(location.search)`); await sleep(500);
check('tapping a league narrows to it, the market kept', /m=1X2/.test(await run('location.search')) && (await run(`document.querySelectorAll('#bets-body .calib-table')[0]?.querySelectorAll('tbody tr').length`)) === 1, await run('location.search'));

// the account box: opens from the menu, shows the forms and the bot check, and answers in place
await open('/clubs?c=39');
await run(`document.querySelector('a.account-btn')?.click()`); await sleep(2500);
check('Sign in opens the account box', (await run(`document.querySelector('#account-title')?.textContent`)) === 'Sign in' && (await run(`!!document.querySelector('#account-modal form[action="/account?/signin"]')`)));
check('the bot check is drawn in the form', await run(`!!document.querySelector('#account-botcheck iframe, #account-botcheck input[name="cf-turnstile-response"]')`));
await run(`[...document.querySelectorAll('#account-body .link-btn')].find((b) => b.textContent === 'Create an account')?.click()`); await sleep(600);
check('Create an account view', (await run(`document.querySelector('#account-title')?.textContent`)) === 'Create an account' && (await run(`document.querySelector('#account-body input[name=password]')?.minLength`)) === 8);
await run(`document.querySelector('#account-modal .modal-close')?.click()`); await sleep(300);
check('the box closes and stays on the page', !(await run(`!!document.querySelector('#account-modal')`)) && (await run('location.pathname')) === '/clubs');
// with no bot-check answer the server refuses, and says so in the box (asked as the form would)
check('a sign-in without the check is refused in words', await run(`fetch('/account?/signin', { method: 'POST', headers: { 'x-sveltekit-action': 'true', 'content-type': 'application/x-www-form-urlencoded' }, body: 'email=nobody%40example.com&password=wrong-password' }).then((r) => r.text()).then((t) => /Wait for the check/.test(t))`));
check('signed out: no session cookie is set', !(await run('document.cookie')).includes('auth-token'));

// a club row on Clubs opens its page
await open('/clubs?c=39');
await run(`document.querySelector('table.clubs tbody tr td:nth-child(4)')?.click()`);
for (let i = 0; i < 20 && !/^\/club\//.test(await run('location.pathname')); i++) await sleep(300); // (a club's page asks for its squad too)
await sleep(600);
check('a Clubs row opens the club page', /^\/club\/\d+$/.test(await run('location.pathname')), await run('location.pathname'));
check('the squad pitch is drawn, in the club\'s colours', (await run(`document.querySelectorAll('.dp-pitch .dp-row').length`)) > 11 && (await run(`getComputedStyle(document.querySelector('.dp-pitch')).getPropertyValue('--kit')`)).startsWith('#'), `${await run(`document.querySelectorAll('.dp-pitch .dp-row').length`)} players`);
check('Best players box beside the table', (await run(`document.querySelectorAll('.club-top .club-mini-table').length`)) === 2);
check('kick-off shown in local time after loading', await run(`!!document.querySelector('time[datetime]')`));

} catch (err) { out.push('STOPPED: ' + err.message.split('\n')[0]); out.push('at ' + await run('location.href') + ' · body: ' + (await run('document.body.innerText.slice(0, 300)'))); }
console.log(out.join('\n'));
console.log(errors.length ? 'PAGE ERRORS:\n' + [...new Set(errors)].join('\n') : 'no page errors');
ws.close(); chrome.kill();
process.exit(out.some((l) => !l.startsWith('ok')) || errors.length ? 1 : 0);
