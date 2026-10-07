// The "rankings" row: one array per club, in the order of `fields`.
export type RankingsDoc = { generated_at: string; fields: string[]; rankings: (number | null)[][] };
export type Club = {
	team: number; league: number; current: number; st: number; lt: number; played: number;
	form: number | null; in_league: number; attack: number; defence: number; home: number; away: number;
	// Gap: Current Strength less Baseline Strength as shown, so the sum adds up
	trend: number;
};
export type Place = { world: number; dom: number | null; domOf: number | null };
export const SORTS = ['lt', 'trend', 'current', 'form'] as const;
export type Sort = (typeof SORTS)[number];

export function clubs(doc: RankingsDoc): Club[] {
	return doc.rankings.map((row) => {
		const c = Object.fromEntries(doc.fields.map((f, i) => [f, row[i]])) as unknown as Club;
		c.trend = Math.round(c.current) - Math.round(c.lt);
		return c;
	});
}

// 1 + how many values are greater: equal values share a place
function placeIn(sorted: number[], v: number) {
	let lo = 0, hi = sorted.length;
	while (lo < hi) {
		const m = (lo + hi) >> 1;
		if (sorted[m] > v) lo = m + 1;
		else hi = m;
	}
	return lo + 1;
}
const desc = (a: number, b: number) => b - a;

// A club's place by Baseline Strength among every ranked club, and among the clubs in its league
// this season.
export function clubPlaces(all: Club[]): Map<number, Place> {
	const world = all.map((c) => c.lt).sort(desc);
	const by = new Map<number, number[]>();
	for (const c of all) if (c.in_league) by.set(c.league, [...(by.get(c.league) || []), c.lt]);
	for (const l of by.values()) l.sort(desc);
	return new Map(all.map((c) => {
		const lg = c.in_league ? by.get(c.league)! : null;
		return [c.team, { world: placeIn(world, c.lt), dom: lg ? placeIn(lg, c.lt) : null, domOf: lg?.length ?? null }];
	}));
}

// The badge colour for a value: its place among every ranked club on that measure. Top 5% is 4
// (green), top 20% 3 (amber), top half 2 (orange), the rest 1 (red).
export function tiers(all: Club[], key: 'current' | 'lt') {
	const sorted = all.map((c) => c[key]).sort(desc);
	return (v: number) => {
		const share = placeIn(sorted, v) / sorted.length;
		return share <= 0.05 ? 4 : share <= 0.2 ? 3 : share <= 0.5 ? 2 : 1;
	};
}

// The Clubs table's rows: clubs playing in a tracked league this season, one league's if asked,
// highest first on the chosen column.
export function clubRows(all: Club[], sort: Sort, league: number | null): Club[] {
	return all
		.filter((c) => c.in_league && (league === null || c.league === league))
		.sort((a, b) => (b[sort] ?? -1e9) - (a[sort] ?? -1e9));
}
