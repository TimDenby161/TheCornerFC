// Which clubs a cup filter shows, from the cup's own file (leagues/<id>).
export type LeagueDoc = {
	fixture_fields: string[];
	fixtures: (string | number | null)[][];
	table_fields: string[];
	table: (string | number | null)[][];
};
type Fixture = {
	kickoff: string; round: string | null; home: number; away: number; status: string;
	hg: number | null; ag: number | null; pen_h: number | null; pen_a: number | null;
};

const OFF = new Set(['CANC', 'PST', 'ABD']);
const CUP_DONE = new Set(['FT', 'AET', 'PEN', 'AWD', 'WO']);

function fixtures(lg: LeagueDoc): Fixture[] {
	return lg.fixtures.map((row) => Object.fromEntries(lg.fixture_fields.map((f, i) => [f, row[i]])) as unknown as Fixture);
}

// A European cup: the league phase once it has a table; before that everyone drawn in it.
export function cupEntrants(lg: LeagueDoc): Set<number> {
	const team = lg.table_fields.indexOf('team');
	if (lg.table.length) return new Set(lg.table.map((r) => r[team] as number));
	return new Set(fixtures(lg).flatMap((f) => [f.home, f.away]));
}

// A domestic cup: the clubs still in. A tie's loser is out (on aggregate, then penalties, then
// whichever of the two doesn't turn up later against someone else). Group matches knock nobody
// out; once knockout ties follow the group stage, the group clubs not in them are out. Clubs yet
// to enter (the Premier League in the FA Cup, say) aren't in the file, so aren't counted.
export function cupTeamsLeft(lg: LeagueDoc): Set<number> {
	const fx = fixtures(lg).filter((f) => !OFF.has(f.status));
	const isGroup = (f: Fixture) => /group/i.test(f.round || '');
	const out = new Set<number>();
	const groupFx = fx.filter(isGroup), koFx = fx.filter((f) => !isGroup(f));
	if (groupFx.length) {
		const groupEnd = groupFx.reduce((m, f) => (f.kickoff > m ? f.kickoff : m), '');
		const after = koFx.filter((f) => f.kickoff > groupEnd);
		if (after.length) {
			const through = new Set(after.flatMap((f) => [f.home, f.away]));
			for (const f of groupFx) for (const t of [f.home, f.away]) if (!through.has(t)) out.add(t);
		}
	}
	const ties = new Map<string, Fixture[]>();
	for (const f of koFx) {
		const key = `${f.round}|${Math.min(f.home, f.away)}|${Math.max(f.home, f.away)}`;
		if (!ties.has(key)) ties.set(key, []);
		ties.get(key)!.push(f);
	}
	const playsLater = (t: number, opp: number, after: string) =>
		koFx.some((f) => f.kickoff > after && (f.home === t || f.away === t) && f.home !== opp && f.away !== opp);
	for (const legs of ties.values()) {
		if (!legs.every((f) => CUP_DONE.has(f.status) && f.hg != null)) continue;
		const a = legs[0].home, b = legs[0].away, last = legs[legs.length - 1];
		const goals = (t: number) => legs.reduce((n, f) => n + ((f.home === t ? f.hg : f.ag) ?? 0), 0);
		let loser = goals(a) > goals(b) ? b : goals(b) > goals(a) ? a : null;
		if (loser == null && last.pen_h != null && last.pen_a != null && last.pen_h !== last.pen_a)
			loser = last.pen_h > last.pen_a ? last.away : last.home;
		if (loser == null) {
			const aOn = playsLater(a, b, last.kickoff), bOn = playsLater(b, a, last.kickoff);
			if (aOn !== bOn) loser = aOn ? b : a;
		}
		if (loser != null) out.add(loser);
	}
	return new Set(fx.flatMap((f) => [f.home, f.away]).filter((t) => !out.has(t)));
}
