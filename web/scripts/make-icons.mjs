// Photographs static/favicon.svg into the icons that can't be SVG (apple-touch-icon.png, icon-192.png,
// icon-512.png, favicon.ico) with headless Chrome, square-cornered because phones round them
// themselves. Run again after changing the mark:
//   node scripts/make-icons.mjs
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = fileURLToPath(new URL('..', import.meta.url));
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const svg = readFileSync(join(web, 'static/favicon.svg'), 'utf8').replace(' rx="16"', '');
const dir = mkdtempSync(join(tmpdir(), 'icons-'));
const page = join(dir, 'icon.html');

// Chrome's window has a minimum width, so the drawing is set to the exact size, not the window's
function photograph(size, out) {
	writeFileSync(page, `<!doctype html><style>html, body { margin: 0; } svg { display: block; width: ${size}px; height: ${size}px; }</style>${svg}`);
	const run = spawnSync(CHROME, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1',
		`--window-size=${size},${size}`, `--screenshot=${out}`, `file://${page}`], { stdio: 'ignore' });
	if (run.status !== 0) process.exit(run.status ?? 1);
	console.log('wrote', out);
}

photograph(180, join(web, 'static/apple-touch-icon.png'));
photograph(192, join(web, 'static/icon-192.png'));
photograph(512, join(web, 'static/icon-512.png'));

// an .ico is a small header and directory around PNGs
const sizes = [32, 48];
const pngs = sizes.map((size) => {
	const out = join(dir, `${size}.png`);
	photograph(size, out);
	return readFileSync(out);
});
const head = Buffer.alloc(6 + 16 * sizes.length);
head.writeUInt16LE(1, 2);
head.writeUInt16LE(sizes.length, 4);
let offset = head.length;
sizes.forEach((size, i) => {
	const at = 6 + 16 * i;
	head[at] = size;
	head[at + 1] = size;
	head.writeUInt16LE(1, at + 4);
	head.writeUInt16LE(32, at + 6);
	head.writeUInt32LE(pngs[i].length, at + 8);
	head.writeUInt32LE(offset, at + 12);
	offset += pngs[i].length;
});
writeFileSync(join(web, 'static/favicon.ico'), Buffer.concat([head, ...pngs]));
console.log('wrote favicon.ico');
