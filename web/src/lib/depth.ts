// A club's squad by position for its next match: who can play where, each player's chance of
// starting there and the minutes he is expected to play. Worked out from the club's own file
// (who started where this season, minutes over 12 months), its players' ranks and its injury
// list. Carried over from the old site's clubDepth, line for line where it could be.
import { formationRoles } from './formations.ts';
import { GROUP_OF, PITCH_SPOTS } from './playerFilters.ts';

export type SquadPlayer = {
	id: number; name: string; position: string | null; rank: number | null;
	position_ranks: Record<string, number> | null; positions_12m: string[] | null;
};
// The club file's "starts": matches this season with a line-up, each player's starts by role,
// every line-up as [player, role, player, role, ...] with its competition and formation, and
// minutes over 12 months as [starts, minutes started, sub appearances, minutes as a sub]
export type Starts = {
	games?: number; players?: Record<string, Record<string, number>>;
	xi?: (number | string)[][]; xi_league?: number[]; xi_formation?: (string | null)[];
	mins?: Record<string, number[]>; mins_matches?: number;
};
export type DepthInput = {
	squad: SquadPlayer[];                       // everyone listed at the club
	out: Set<number>;                           // injured or suspended: left off the pitch
	starts?: Starts;
	positions?: Record<string, [string, number][]>;   // each player's starting minutes by role over 12 months
	seasonFormations: (string | null)[];        // this season's matches' formations
	// the next match's kind of competition ("league", "europe", "cup"), and each line-up's
	nextGroup: string | null;
	groupOf: (league: number) => string;
};
export type Box = {
	label: string; roles: string[]; row: number | string; col: number; n: number; exact: number;
	ps: { p: SquadPlayer; rank: number | null }[]; proj: { share: Map<number, number>; changed: boolean } | null;
};
export type Depth = {
	shown: Box[]; startChance: Map<string, number>; xMins: Map<string, number>; boxMins: Map<string, number>;
	picks: Map<string, number[]>; startPct: (p: SquadPlayer, roles: string[]) => number | null;
	lasts: (p: SquadPlayer) => number; benchRate: (p: SquadPlayer) => number;
};

const NEAR_GROUP: Record<string, string> = { FB: 'WB', WB: 'FB' }; // a full-back with no wing-back rank is shown there on his full-back one, and the other way round
const DEPTH_MINUTES = 180;
const ABILITY_PULL = 0.2;
// a squad player with no box goes in the nearest one the club uses
const NEAR: Record<string, string[]> = {
	LWB: ['LB', 'LM', 'CB'], RWB: ['RB', 'RM', 'CB'], LB: ['LWB', 'CB'], RB: ['RWB', 'CB'],
	LW: ['LM', 'AM', 'ST'], RW: ['RM', 'AM', 'ST'], LM: ['LW', 'CM', 'AM'], RM: ['RW', 'CM', 'AM'],
	AM: ['CM', 'LW', 'RW', 'ST'], DM: ['CM', 'CB'], CM: ['CM', 'AM'], ST: ['AM', 'LW', 'RW'], CB: ['LB', 'RB', 'CM']
};
const PARTNER: Record<string, string> = { LM: 'LW', LW: 'LM', RM: 'RW', RW: 'RM', LWB: 'LB', LB: 'LWB', RWB: 'RB', RB: 'RWB', AM: 'CM', CM: 'AM', ST: 'AM' };

export function clubDepth(input: DepthInput): Depth | null {
	const { out, starts: st, positions, nextGroup, groupOf } = input;
	const atClub = new Set(input.squad.map((p) => p.id));
	const squad = input.squad.filter((p) => !out.has(p.id));
	if (!squad.length) return null;
	const group = (r: string | null) => (r ? GROUP_OF[r] : undefined);
	const rankAt = (p: SquadPlayer, r: string): number | null =>
		p.position_ranks?.[group(r)!] ?? p.position_ranks?.[NEAR_GROUP[group(r)!]] ?? (group(p.position) === group(r) ? p.rank : null);
	// who can play where: his main position, or 2+ full matches' worth of starting minutes there
	// over the last 12 months (until those are known, the 25% rule of the position filter)
	const canPlay = (p: SquadPlayer): Set<string | null> => {
		const rows = positions?.[String(p.id)];
		if (!rows) return new Set([p.position, ...(p.positions_12m || [])]);
		return new Set([p.position, ...rows.filter(([r, m]) => r !== 'SUB' && m >= DEPTH_MINUTES).map(([r]) => r)]);
	};
	// only the positions in the formations the club has used (all of them if none are known); a
	// formation used only once this season is left out, unless none has been used more than once
	const formationCount = new Map<string, number>();
	for (const f of input.seasonFormations) if (f) formationCount.set(f, (formationCount.get(f) || 0) + 1);
	const oneOff = new Set([...formationCount.values()].some((n) => n > 1) ? [...formationCount].filter(([, n]) => n === 1).map(([f]) => f) : []);
	const used = new Set([...formationCount.keys()].filter((f) => !oneOff.has(f)).flatMap(formationRoles));
	// one box per position; DM and CM share one central-midfield box over both lines
	const boxes: { label: string; roles: string[]; row: number | string; col: number }[] = PITCH_SPOTS.filter(([r]) => r !== 'DM' && r !== 'CM').map(([r, x, y]) =>
		({ label: r, roles: [r], row: y < 20 ? 6 : y < 35 ? 5 : y < 50 ? 4 : y < 65 ? 3 : y < 80 ? 2 : 1, col: x < 35 ? 3 : x < 65 ? 2 : 1 }));
	boxes.push({ label: 'CM', roles: ['DM', 'CM'], row: '3 / span 2', col: 2 });
	// his share of the club's matches this season (with a line-up) that he started in this box
	const startPct = (p: SquadPlayer, roles: string[]) => {
		const n = roles.reduce((a, r) => a + (st?.players?.[String(p.id)]?.[r] || 0), 0);
		return st?.games && n ? Math.round((100 * n) / st.games) : null;
	};
	const usualExact = (roles: string[]) => (st?.games ? Object.values(st.players || {})
		.reduce((a, byRole) => a + roles.reduce((b, r) => b + (byRole[r] || 0), 0), 0) / st.games : 0);
	const xiFormation = st?.xi_formation || [];
	const keep = (_: unknown, k: number) => !oneOff.has(xiFormation[k] as string);
	const xi = (st?.xi || []).filter(keep), xiLeague = (st?.xi_league || []).filter(keep);
	const seasonXi = xi;
	const groupXi = nextGroup ? xi.filter((_, k) => groupOf(xiLeague[k]) === nextGroup) : [];
	const wGroup = groupXi.length / (groupXi.length + 1);
	type Xi = (number | string)[][];
	const perMatch = (matches: Xi, roles: string[]) => (matches.length ? matches.reduce((t, m) => {
		for (let i = 0; i < m.length; i += 2) if (roles.includes(m[i + 1] as string)) t++;
		return t;
	}, 0) / matches.length : null);
	const exactFor = (roles: string[]) => {
		const all = perMatch(xi, roles) ?? usualExact(roles);
		return groupXi.length ? wGroup * perMatch(groupXi, roles)! + (1 - wGroup) * all : all;
	};
	const shareIn = (matches: Xi, p: SquadPlayer, roles: string[]) => {
		if (!matches.length) return 0;
		let c = 0;
		for (const m of matches) for (let i = 0; i < m.length; i += 2) if (m[i] === p.id && roles.includes(m[i + 1] as string)) c++;
		return (100 * c) / matches.length;
	};
	type Ps = { p: SquadPlayer; rank: number | null }[];
	// The share each available player is expected to start in a box: his own starts there this
	// season, plus a cut of the starts of players now injured or gone. That missing share goes to
	// the players who have started there since the last of them did, then to the others by rank
	// (each 3 points lower halves it), each start there this season adding one more share; nobody
	// over 100%. Only players who really play there take it.
	const projectedIn = (roles: string[], n: number, ps: Ps, xi: Xi) => {
		const actual = new Map(ps.map(({ p }) => [p.id, shareIn(xi, p, roles)]));
		const share = new Map(actual);
		let left = n * 100 - [...actual.values()].reduce((a, v) => a + v, 0);
		if (left <= 0.5) return { share, changed: false };
		let last = -1;
		xi.forEach((m, k) => {
			for (let i = 0; i < m.length; i += 2) if (roles.includes(m[i + 1] as string) && (out.has(m[i] as number) || !atClub.has(m[i] as number))) last = k;
		});
		if (last < 0) return { share, changed: false }; // short only because the formation varies
		const startsIn = (id: number, inBox: boolean, matches: Xi = xi) => matches.reduce((t, m) => {
			for (let i = 0; i < m.length; i += 2) if (m[i] === id && roles.includes(m[i + 1] as string) === inBox) t++;
			return t;
		}, 0);
		const season = seasonXi; // a start there in any competition counts
		const regular = ps.filter(({ p }) => roles.some((x) => canPlay(p).has(x))
			|| (startsIn(p.id, true, season) && startsIn(p.id, false, season) <= season.length / 2));
		const pool = regular.length ? regular : ps;
		const room = (id: number) => 100 - share.get(id)!;
		const hand = (weights: [number, number][]) => { // share out what's left by these weights
			const wsum = weights.reduce((a, [, w]) => a + w, 0);
			if (left <= 0.5 || !wsum) return;
			const give = left;
			for (const [id, w] of weights) { const g = Math.min(room(id), (give * w) / wsum); share.set(id, share.get(id)! + g); left -= g; }
		};
		const since = new Map<number, number>();
		for (const m of xi.slice(last + 1)) for (let i = 0; i < m.length; i += 2)
			if (roles.includes(m[i + 1] as string)) since.set(m[i] as number, (since.get(m[i] as number) || 0) + 1);
		hand(pool.map(({ p }) => [p.id, since.get(p.id) || 0]));
		const top = Math.max(...pool.map((d) => d.rank as number));
		hand(pool.map(({ p, rank }) => [p.id, 2 ** (((rank as number) - top) / 3) * (1 + startsIn(p.id, true))]));
		for (const { p } of pool) { if (left <= 0.5) break; const g = Math.min(room(p.id), left); share.set(p.id, share.get(p.id)! + g); left -= g; }
		return { share, changed: true };
	};
	// for the next match's kind of competition: this season's matches of that kind, blended with
	// all its matches in proportion k : 1 (k = matches of that kind)
	const projected = (roles: string[], n: number, ps: Ps) => {
		const all = projectedIn(roles, n, ps, xi);
		if (!groupXi.length) return all;
		const grp = projectedIn(roles, n, ps, groupXi);
		const share = new Map(ps.map(({ p }) => [p.id, wGroup * (grp.share.get(p.id) || 0) + (1 - wGroup) * (all.share.get(p.id) || 0)]));
		return { share, changed: all.changed || grp.changed };
	};
	const visible = boxes.filter((b) => !used.size || b.roles.some((r) => used.has(r)));
	// who can play in a box, and anyone who has started there this season
	const fits = (p: SquadPlayer, b: { roles: string[] }) => b.roles.some((x) => canPlay(p).has(x)) || startPct(p, b.roles);
	const labels = new Set(visible.map((b) => b.label));
	const fallback = new Map(squad.filter((p) => !visible.some((b) => fits(p, b)))
		.map((p) => [p.id, (NEAR[p.position as string] || []).find((l) => labels.has(l)) || (labels.has('CM') ? 'CM' : null)]));
	// Starters per box: its starters per match rounded to whole players that make an XI, the
	// largest fractions taking the places left after rounding down
	const exactOf = new Map(visible.map((b) => [b.label, exactFor(b.roles)]));
	const starters = new Map([...exactOf].map(([l, x]) => [l, Math.floor(x)]));
	let places = [...exactOf.values()].some((x) => x > 0) ? 11 - [...starters.values()].reduce((t, x) => t + x, 0) : 0;
	for (const [l, x] of [...exactOf].sort((a, b) => (b[1] % 1) - (a[1] % 1))) {
		if (places <= 0 || x % 1 === 0) break;
		starters.set(l, starters.get(l)! + 1);
		places--;
	}
	const shown: Box[] = visible.map((b) => {
		const n = starters.get(b.label)!;
		const ps = squad.filter((p) => fits(p, b) || fallback.get(p.id) === b.label)
			.map((p) => ({ p, rank: Math.max(...b.roles.map((x) => rankAt(p, x) ?? -1)) }))
			.map((d) => ({ ...d, rank: d.rank >= 0 ? d.rank : d.p.rank }))
			.sort((x, y) => (y.rank as number) - (x.rank as number));
		return { ...b, n, exact: n, ps, proj: ps.length ? projected(b.roles, n, ps) : null };
	});
	// The best XI by rating: the usual number of starters in each box, filled from the highest
	// player-and-position ranks down, one position per player. A pick only counts if he's rated
	// above one of the box's usual starters or is one himself. The expected share is ABILITY_PULL
	// of that and the rest history.
	const picks = new Map<string, number[]>(), placed = new Set<number>(), filled = new Map<string, number>();
	const histOf = (b: Box, id: number) => b.proj?.share.get(id) || 0;
	shown.flatMap((b) => (b.n ? b.ps.map((d) => ({ b, ...d, h: histOf(b, d.p.id) })) : []))
		.sort((x, y) => (y.rank as number) - (x.rank as number) || y.h - x.h).forEach(({ b, p }) => {
			if (placed.has(p.id) || (filled.get(b.label) || 0) >= b.n) return;
			placed.add(p.id);
			filled.set(b.label, (filled.get(b.label) || 0) + 1);
			if (!picks.has(b.label)) picks.set(b.label, []);
			picks.get(b.label)!.push(p.id);
		});
	const ability = new Map<string, Map<number, number>>();
	for (const b of shown) {
		if (!b.n || !b.ps.length) continue;
		const usual = [...b.ps].sort((x, y) => histOf(b, y.p.id) - histOf(b, x.p.id)).slice(0, b.n);
		const worst = Math.min(...usual.map((d) => d.rank as number));
		const rankOf = new Map(b.ps.map((d) => [d.p.id, d.rank as number]));
		const count = (picks.get(b.label) || []).filter((id) => usual.some((d) => d.p.id === id) || rankOf.get(id)! > worst);
		const rest = b.ps.filter((d) => !count.includes(d.p.id));
		const restHist = rest.reduce((a, d) => a + histOf(b, d.p.id), 0);
		const left = Math.max(0, b.n - count.length) * 100;
		ability.set(b.label, new Map(b.ps.map((d) => [d.p.id, count.includes(d.p.id) ? 100 : restHist ? (left * histOf(b, d.p.id)) / restHist : 0])));
	}
	// Start chance per player and box: history with the pull towards the best XI
	const startChance = new Map<string, number>(); // "box:player" -> %
	for (const { label: r, ps, proj } of shown) {
		const ab = ability.get(r);
		for (const { p } of ps) {
			const hist = proj?.share.get(p.id) || 0;
			startChance.set(`${r}:${p.id}`, ab ? (1 - ABILITY_PULL) * hist + ABILITY_PULL * Math.min(100, ab.get(p.id) || 0) : hist);
		}
	}
	// A player starts in one position at most: his chances across boxes can't pass 100%. Over it,
	// he keeps his likeliest positions and gives up the rest; each box then tops its starts back
	// up from its other players with room, by their chance there (or their rank if nobody has one)
	const totalChance = (id: number) => shown.reduce((t, b) => t + (startChance.get(`${b.label}:${id}`) || 0), 0);
	const everyone = () => new Set(shown.flatMap((b) => b.ps.map(({ p }) => p.id)));
	for (const id of everyone()) {
		let cap = 100;
		for (const b of [...shown].sort((x, y) => (startChance.get(`${y.label}:${id}`) || 0) - (startChance.get(`${x.label}:${id}`) || 0))) {
			const k = `${b.label}:${id}`;
			if (!startChance.has(k)) continue;
			const v = Math.min(startChance.get(k)!, cap);
			startChance.set(k, v);
			cap -= v;
		}
	}
	for (const b of shown) {
		let left = b.exact * 100 - b.ps.reduce((t, { p }) => t + startChance.get(`${b.label}:${p.id}`)!, 0);
		if (left < -0.5) { // over its starters: scale the box down to them
			const k = (b.exact * 100) / (b.exact * 100 - left);
			for (const { p } of b.ps) startChance.set(`${b.label}:${p.id}`, startChance.get(`${b.label}:${p.id}`)! * k);
			left = 0;
		}
		for (const pass of ['chance', 'rank']) {
			if (left <= 0.5) break;
			const w = b.ps.map(({ p, rank }) => [p.id, pass === 'chance' ? startChance.get(`${b.label}:${p.id}`)! : (rank as number)] as [number, number]).filter(([, v]) => v > 0);
			const wsum = w.reduce((t, [, v]) => t + v, 0);
			const give = left;
			for (const [id, v] of w) {
				const k = `${b.label}:${id}`;
				const g = Math.min((give * v) / wsum, 100 - totalChance(id), 100 - startChance.get(k)!);
				if (g > 0) { startChance.set(k, startChance.get(k)! + g); left -= g; }
			}
		}
	}
	// Expected minutes in each box: as a starter, his start chance x how long he usually lasts
	// when he starts; off the bench, the minutes the box's starters are expected to leave shared
	// among the squad players whose main position is there, by their minutes per match off the
	// bench; nobody over 90 in all
	const mins = st?.mins || {}, minsMatches = st?.mins_matches || 0;
	const lasts = (p: SquadPlayer) => {
		const [n = 0, m = 0] = mins[String(p.id)] || [], typical = group(p.position) === 'GK' ? 90 : 80;
		return (m + 3 * typical) / (n + 3);
	};
	const benchRate = (p: SquadPlayer) => (minsMatches ? ((mins[String(p.id)] || [])[3] || 0) / minsMatches : 0);
	const mainBox = (p: SquadPlayer) => shown.find((b) => b.roles.includes(p.position as string))?.label;
	const xMins = new Map<string, number>(), boxMins = new Map<string, number>();
	for (const { label: r, exact, ps } of shown) {
		let starting = 0;
		for (const { p } of ps) {
			const m = (startChance.get(`${r}:${p.id}`)! / 100) * lasts(p);
			xMins.set(`${r}:${p.id}`, m);
			starting += m;
		}
		const demand = Math.max(0, exact * 90 - starting);
		const notStarting = ({ p }: { p: SquadPlayer }) => Math.max(0, 100 - totalChance(p.id)) / 100;
		const subW = ({ p }: { p: SquadPlayer }) => benchRate(p) * notStarting({ p });
		let bench = ps.filter((d) => mainBox(d.p) === r && subW(d) > 0);
		if (!bench.length) bench = ps.filter((d) => subW(d) > 0);
		const weight = bench.length ? subW : notStarting;
		if (!bench.length) bench = ps;
		const wsum = bench.reduce((t, d) => t + weight(d), 0);
		if (wsum) for (const d of bench) xMins.set(`${r}:${d.p.id}`, xMins.get(`${r}:${d.p.id}`)! + (demand * weight(d)) / wsum);
	}
	for (const id of everyone()) {
		const keys = shown.map((b) => `${b.label}:${id}`).filter((k) => xMins.has(k));
		let over = keys.reduce((t, k) => t + xMins.get(k)!, 0) - 90;
		for (const k of [...keys].sort((x, y) => xMins.get(x)! - xMins.get(y)!)) {
			if (over <= 0) break;
			const cut = Math.min(over, xMins.get(k)!);
			xMins.set(k, xMins.get(k)! - cut);
			over -= cut;
		}
	}
	const playerMins = (id: number) => shown.reduce((t, b) => t + (xMins.get(`${b.label}:${id}`) || 0), 0);
	const topUp = (need: number, into: string) => { // give `need` minutes to box `into`'s players
		const b = shown.find((x) => x.label === into);
		if (!b) return need;
		for (let pass = 0; pass < 2; pass++) {
			const w = b.ps.map(({ p, rank }) => [p.id, rank as number, 90 - playerMins(p.id)] as [number, number, number]).filter(([, , room]) => room > 0.01);
			const wsum = w.reduce((t, [, r]) => t + r, 0);
			if (!wsum || need <= 0.01) break;
			const give = need;
			for (const [id, r, room] of w) {
				const g = Math.min(room, (give * r) / wsum);
				xMins.set(`${into}:${id}`, (xMins.get(`${into}:${id}`) || 0) + g);
				need -= g;
			}
		}
		return need;
	};
	for (const b of shown) {
		const short = b.exact * 90 - b.ps.reduce((t, { p }) => t + (xMins.get(`${b.label}:${p.id}`) || 0), 0);
		if (short > 0.01) { const rest = topUp(short, b.label); if (rest > 0.01 && PARTNER[b.label]) topUp(rest, PARTNER[b.label]); }
	}
	for (const { label: r, ps } of shown) {
		// whole minutes that add up to the box's total (largest remainders get the spare minutes)
		const raw = ps.map(({ p }) => [p.id, Math.min(90, xMins.get(`${r}:${p.id}`) || 0)] as [number, number]);
		const total = Math.round(raw.reduce((t, [, v]) => t + v, 0));
		const whole = new Map(raw.map(([id, v]) => [id, Math.floor(v)]));
		let spare = total - [...whole.values()].reduce((t, v) => t + v, 0);
		for (const [id] of [...raw].sort((x, y) => (y[1] % 1) - (x[1] % 1))) { if (spare <= 0) break; whole.set(id, whole.get(id)! + 1); spare--; }
		for (const [id, v] of whole) xMins.set(`${r}:${id}`, v);
		boxMins.set(r, total);
	}
	return { shown, startChance, xMins, boxMins, picks, startPct, lasts, benchRate };
}

// The predicted XI from the start chances: each position's usual number of starters, one position
// per player, filled from the surest picks down
export type XiPick = { box: Box; p: SquadPlayer; rank: number | null; chance: number; mins: number };
export function predictedXi(d: Depth | null): XiPick[] | null {
	if (!d) return null;
	const filled = new Map<string, number>(), placed = new Set<number>(), xi: XiPick[] = [];
	d.shown.flatMap((b) => (b.n ? b.ps.map(({ p, rank }) => ({ box: b, p, rank, chance: d.startChance.get(`${b.label}:${p.id}`) || 0 })) : []))
		.filter((c) => c.chance > 0).sort((x, y) => y.chance - x.chance || (y.rank as number) - (x.rank as number)).forEach((c) => {
			if (placed.has(c.p.id) || (filled.get(c.box.label) || 0) >= c.box.n) return;
			placed.add(c.p.id);
			filled.set(c.box.label, (filled.get(c.box.label) || 0) + 1);
			xi.push({ ...c, mins: d.xMins.get(`${c.box.label}:${c.p.id}`) || 0 });
		});
	return xi.length ? xi : null;
}

// The expected squad's strength: the minutes-weighted average position rank of everyone expected
// to play (bench minutes too); attack and defence weight each position by how much it attacks or
// defends
const SQUAD_WEIGHTS: Record<string, [number, number]> = { // [attack, defence]
	GK: [0, 1], CB: [0.1, 1], LB: [0.3, 0.8], RB: [0.3, 0.8], LWB: [0.4, 0.6], RWB: [0.4, 0.6],
	CM: [0.5, 0.6], LM: [0.8, 0.3], RM: [0.8, 0.3], AM: [1, 0.2], LW: [1, 0.15], RW: [1, 0.15], ST: [1, 0.1]
};
export function squadStrength(d: Depth | null): { strength: number; attack: number | null; defence: number | null } | null {
	if (!d) return null;
	const sum = { all: [0, 0], att: [0, 0], def: [0, 0] };
	for (const b of d.shown) {
		const [wa, wd] = SQUAD_WEIGHTS[b.label] || [0.5, 0.5];
		for (const { p, rank } of b.ps) {
			const m = d.xMins.get(`${b.label}:${p.id}`) || 0, r = rank as number;
			sum.all[0] += r * m; sum.all[1] += m;
			sum.att[0] += r * m * wa; sum.att[1] += m * wa;
			sum.def[0] += r * m * wd; sum.def[1] += m * wd;
		}
	}
	const avg = ([a, b]: number[]) => (b ? a / b : null);
	return sum.all[1] ? { strength: avg(sum.all)!, attack: avg(sum.att), defence: avg(sum.def) } : null;
}

// Where the XI stands on its pitch: keeper at the top, attacking down, left-sided positions on
// the right. Players on the same line that would sit too close are spread evenly around their
// middle, 24% apart (less if that won't fit). A wide player whose line is only just off a central
// one's (a full-back beside two centre-backs, a wide midfielder beside two central ones) is then
// moved out towards the touchline until he is 24% from him too. x and y are % of the pitch.
export function xiSpots<T extends { box: { label: string } }>(xi: T[]): { c: T; x: number; y: number }[] {
	const spot: Record<string, [number, number]> = Object.fromEntries(PITCH_SPOTS.map(([r, x, y]) => [r, [x, y]]));
	Object.assign(spot, { LM: [18, 34], RM: [82, 34] });
	const lines = new Map<number, { c: T; x: number }[]>();
	for (const c of xi) {
		const [x0, y0] = spot[c.box.label] || spot.CM;
		const x = 100 - x0, y = Math.round(100 - y0) + (y0 > 85 ? 1 : 0);
		if (!lines.has(y)) lines.set(y, []);
		lines.get(y)!.push({ c, x });
	}
	const placed = [...lines].flatMap(([y, ps]) => {
		ps.sort((a, b) => a.x - b.x);
		const xs = ps.map((q) => q.x);
		const clash = xs.some((v, i) => i && v - xs[i - 1] < 22);
		const gap = Math.min(24, 72 / Math.max(1, ps.length - 1)), width = gap * (ps.length - 1);
		const from = Math.min(Math.max(xs.reduce((a, v) => a + v, 0) / xs.length - width / 2, 14), 86 - width);
		return ps.map((q, i) => ({ c: q.c, x: clash ? from + i * gap : q.x, y }));
	});
	// lines under 10% apart are closer than a player's box is tall
	for (const p of placed) for (const q of placed) {
		if (p.y === q.y || Math.abs(p.y - q.y) >= 10 || Math.abs(p.x - q.x) >= 22) continue;
		if (Math.abs(p.x - 50) <= Math.abs(q.x - 50)) continue; // the wider of the two is the one that moves
		p.x = p.x > 50 ? Math.min(86, q.x + 24) : Math.max(14, q.x - 24);
	}
	return placed;
}
