// Draws the card a shared link shows (static/share-card.png, 1200 x 630, named by
// lib/server/share.ts): the site's pitch green, chalk lines and Archivo, photographed by headless
// Chrome so the type is the site's own. Run again after changing the look:
//   node scripts/make-share-card.mjs
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = fileURLToPath(new URL('..', import.meta.url));
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const font = join(web, 'src/styles/fonts/archivo-latin.woff2');

const html = `<!doctype html><meta charset="utf-8"><style>
@font-face { font-family: Archivo; src: url("file://${font}") format("woff2"); font-weight: 100 900; font-stretch: 62% 125%; }
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; }
body { background: #0e3b29; color: #f2f4ec; font-family: Archivo, sans-serif; position: relative; }
svg { position: absolute; inset: 0; }
.text { position: absolute; left: 96px; top: 168px; }
h1 { margin: 0; font-size: 112px; font-weight: 800; font-stretch: 75%; letter-spacing: -1px; line-height: 1; }
p { margin: 28px 0 0; font-size: 38px; font-weight: 400; opacity: .92; }
.url { position: absolute; left: 96px; bottom: 64px; font-size: 28px; font-weight: 600; font-stretch: 87%; letter-spacing: 1px; opacity: .8; }
</style>
<svg width="1200" height="630" viewBox="0 0 1200 630" fill="none" stroke="#f2f4ec" stroke-opacity=".14" stroke-width="4">
  <!-- the corner the site is named for: the touchline, the goal line and the corner arc -->
  <path d="M1200 630 H760 M1200 630 V190" />
  <path d="M1200 560 A70 70 0 0 0 1130 630" stroke-opacity=".35" />
  <!-- the penalty box and the D, faint, running off the page -->
  <path d="M1200 210 H1010 V630" /><path d="M1010 330 A120 120 0 0 0 1010 510" />
  <line x1="1196" y1="630" x2="1196" y2="520" stroke-opacity=".6" />
  <path d="M1196 520 l-34 14 l34 14 z" fill="#ff86c0" stroke="none" />
</svg>
<div class="text"><h1>The Corner FC</h1><p>Club ratings · Player ranks · Match predictions</p></div>
<div class="url">THECORNERFC.COM</div>`;

const dir = mkdtempSync(join(tmpdir(), 'share-card-'));
const page = join(dir, 'card.html');
writeFileSync(page, html);
const out = join(web, 'static/share-card.png');
const run = spawnSync(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
	'--window-size=1200,630', `--screenshot=${out}`, '--allow-file-access-from-files', `file://${page}`], { stdio: 'inherit' });
if (run.status !== 0) process.exit(run.status ?? 1);
console.log('wrote', out);
