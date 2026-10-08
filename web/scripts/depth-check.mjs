// Is the squad model in src/lib/depth.ts the same as the old site's? This runs the old site's own
// clubDepth (cut out of docs/assets/app.js, with stand-ins for the page around it) and the new one
// on the same clubs, and compares every start chance, expected minute, predicted XI and squad
// strength. Players' ranks are made up here (the same for both), since a visitor who isn't signed
// in is sent few of them and the model needs them all to be worth comparing.
//   node scripts/depth-check.mjs [club ids ...]
import { readFileSync } from 'node:fs';
import { clubDepth, predictedXi, squadStrength } from '../src/lib/depth.ts';
import { clubMatches, clubSeasons } from '../src/lib/club.ts';
import { SUPABASE } from '../src/lib/config.ts';

const src = readFileSync(new URL('../../docs/assets/app.js', import.meta.url), 'utf8');
function cut(start) { // a function or const from app.js: from `start` to the end of its statement
	const i = src.indexOf(start);
	if (i < 0) throw new Error(`not in app.js: ${start}`);
	let depth = 0, quote = null, seenBrace = false;
	for (let k = i; k < src.length; k++) {
		const ch = src[k];
		if (quote) { if (ch === '\\') k++; else if (ch === quote) quote = null; continue; }
		if (ch === '/' && src[k + 1] === '/') { k = src.indexOf('\n', k); continue; }
		if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
		if ('([{'.includes(ch)) { depth++; if (ch === '{') seenBrace = true; }
		else if (')]}'.includes(ch)) { depth--; if (depth === 0 && ch === '}' && start.startsWith('function') && seenBrace) return src.slice(i, k + 1); }
		else if (ch === ';' && depth === 0 && !start.startsWith('function')) return src.slice(i, k + 1);
	}
	throw new Error(`no end: ${start}`);
}
const old = new Function('state', 'clubCache', 'clubInjuries', 'clubUpcoming', `
	${['const SHORT_NAMES =', 'const PITCH_SPOTS =', 'const GROUP_OF =', 'const NEAR_GROUP =', 'const DEPTH_MINUTES =', 'const seasonShort =', 'const playsAt =', 'const SQUAD_WEIGHTS =',
		'function formationRoles(', 'function clubSeasons(', 'function clubFormationRows(', 'function canPlay(', 'function clubDepth(', 'function predictedXi(', 'function squadStrength('].map(cut).join('\n')}
	return { clubDepth, predictedXi, squadStrength, clubFormationRows };`);

const ask = async (path, body) => {
	const r = body ? await fetch(`${SUPABASE.url}/rest/v1/rpc/${path}`, { method: 'POST', headers: { apikey: SUPABASE.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
		: await fetch(`${SUPABASE.url}/rest/v1/rpc/site_doc?p_key=${path}&apikey=${SUPABASE.key}`);
	if (!r.ok) throw new Error(`${path}: ${r.status}`);
	return r.json();
};
const site = await ask('site'), injuries = await ask('injuries');
const GROUP_OF = { GK: 'GK', CB: 'CB', LB: 'FB', RB: 'FB', LWB: 'WB', RWB: 'WB', DM: 'DM', CM: 'CM', LM: 'W', RM: 'W', AM: 'AM', LW: 'W', RW: 'W', ST: 'ST' };
const made = (id, salt) => { let x = Math.imul(id ^ (salt * 2654435761), 1597334677) >>> 0; x ^= x >>> 15; return (x % 5500) / 100 + 40; }; // 40 to 95, the same every run
const compGroup = (lg) => { const c = site.competitions[lg]; return !c ? 'cup' : c.type === 'League' ? 'league' : c.country === 'World' ? 'europe' : 'cup'; };
const near = (a, b) => (a == null || b == null ? a == b : Math.abs(a - b) < 1e-9);

let bad = 0;
for (const id of (process.argv.slice(2).length ? process.argv.slice(2) : ['42', '50', '157', '529', '40', '33', '1603', '63', '746', '211']).map(Number)) {
	const doc = await ask(`clubs/${id}`);
	const answer = await ask('site_players', { p_teams: [id], p_limit: 2000 });
	const list = answer.rows.map((r) => {
		const p = Object.fromEntries(site.player_fields.map((f, i) => [f, r[i]]));
		p.rank = made(p.id, 1);
		const groups = new Set([p.position, ...(p.positions_12m || [])].map((x) => GROUP_OF[x]).filter(Boolean));
		p.position_ranks = GROUP_OF[p.position] === 'GK' ? null : Object.fromEntries([...groups].map((g, k) => [g, k === 0 ? p.rank : made(p.id, 2 + k)]));
		return p;
	});
	const matches = (await ask('site_matches', { p_team: id })).matches.map((r) => Object.fromEntries(site.match_fields.map((f, i) => [f, r[i]])))
		.sort((a, b) => a.kickoff.localeCompare(b.kickoff) || a.id - b.id);
	const next = matches.find((m) => !['FT', 'AET', 'PEN', 'AWD', 'WO', 'CANC', 'PST', 'ABD'].includes(m.status)) || null;
	const inj = injuries.teams?.[String(id)] || null;

	// the old site's
	const data = { ...doc, rows: doc.matches.map((r) => Object.fromEntries(doc.fields.map((f, i) => [f, r[i]]))) };
	const o = old({ players: { list }, data: { competitions: site.competitions }, club: { id, data } }, new Map([[id, data]]), () => inj, () => (next ? [next] : []));
	const od = o.clubDepth(id, data, null);

	// the new one
	const rows = clubMatches(doc);
	const { seasonOf } = clubSeasons(rows);
	const season = rows.length ? seasonOf(rows[rows.length - 1]) : null;
	const nd = clubDepth({
		squad: list, out: new Set((inj?.players || []).map(([pid]) => pid)), starts: doc.starts, positions: doc.positions,
		seasonFormations: rows.filter((m) => seasonOf(m) === season).map((m) => m.formation),
		nextGroup: next ? compGroup(next.league) : null, groupOf: compGroup
	});

	const diffs = [];
	if (!od !== !nd) diffs.push('one has no squad');
	else if (od) {
		const boxes = (d) => d.shown.map((b) => `${b.label}:${b.n}:${b.row}:${b.col}:${b.ps.map((x) => x.p.id).join(',')}`).join(' | ');
		if (boxes(od) !== boxes(nd)) diffs.push('boxes differ');
		for (const name of ['startChance', 'xMins', 'boxMins']) {
			const a = od[name], b = nd[name];
			if (a.size !== b.size) diffs.push(`${name}: ${a.size} against ${b.size}`);
			for (const [k, v] of a) if (!near(v, b.get(k))) { diffs.push(`${name} ${k}: ${v} against ${b.get(k)}`); break; }
		}
		const xi = (list) => (list || []).map((c) => `${(c.b || c.box).label}:${c.p.id}:${c.mins}`).join(' ');
		if (xi(o.predictedXi(id, data, null)) !== xi(predictedXi(nd))) diffs.push('predicted XI differs');
		const os = o.squadStrength(id, data, null), ns = squadStrength(nd);
		if (!os !== !ns || (os && !(near(os.strength, ns.strength) && near(os.attack, ns.attack) && near(os.defence, ns.defence)))) diffs.push('squad strength differs');
	}
	bad += diffs.length;
	console.log(`${diffs.length ? 'FAIL' : 'ok  '} ${site.teams[id] || id}: ${od ? `${od.shown.length} boxes, ${od.startChance.size} start chances, XI of ${(predictedXi(nd) || []).length}` : 'no squad'}${diffs.length ? ' — ' + diffs.slice(0, 3).join('; ') : ''}`);
}
process.exit(bad ? 1 : 0);
